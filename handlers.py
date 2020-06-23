"""
ASGI config for sse project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/dev/howto/deployment/asgi/
"""
import logging
import os

import django
from asgiref.sync import sync_to_async
from django.core import signals
from django.core.exceptions import RequestAborted
from django.core.handlers.asgi import ASGIHandler as DjangoASGIHandler
from django.http import FileResponse
from django.urls import set_script_prefix

from concurrency import run_until_first_complete


logger = logging.getLogger(__name__)


class ASGIHandler(DjangoASGIHandler):
    async def __call__(self, scope, receive, send):
        """
        Async entrypoint - parses the request and hands off to get_response.
        """
        # Serve only HTTP connections.
        # FIXME: Allow to override this.
        if scope['type'] != 'http':
            raise ValueError(
                'Django can only handle ASGI/HTTP connections, not %s.'
                % scope['type']
            )
        # Receive the HTTP request body as a stream object.
        try:
            body_file = await self.read_body(receive)
        except RequestAborted:
            return
        # Request is complete and can be served.
        set_script_prefix(self.get_script_prefix(scope))
        await sync_to_async(signals.request_started.send)(sender=self.__class__, scope=scope)
        # Get the request and check for basic issues.
        request, error_response = self.create_request(scope, body_file)
        if request is None:
            await self.send_response(error_response, send)
            return
        # Get the response, using the async mode of BaseHandler.
        response = await self.get_response_async(request)
        response._handler_class = self.__class__
        # Increase chunk size on file responses (ASGI servers handles low-level
        # chunking).
        if isinstance(response, FileResponse):
            response.block_size = self.chunk_size
        # Send the response.
        if response.streaming:
            await run_until_first_complete(
                (self.send_response, {"response": response, "send": send}),
                (self.listen_for_disconnect, {"receive": receive})
            )
        else:
            await self.send_response(response, send)

    async def listen_for_disconnect(self, receive) -> None:
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break

    async def send_response(self, response, send):
        """Encode and send a response out over ASGI."""
        # Collect cookies into headers. Have to preserve header case as there
        # are some non-RFC compliant clients that require e.g. Content-Type.
        response_headers = []
        for header, value in response.items():
            if isinstance(header, str):
                header = header.encode('ascii')
            if isinstance(value, str):
                value = value.encode('latin1')
            response_headers.append((bytes(header), bytes(value)))
        for c in response.cookies.values():
            response_headers.append(
                (b'Set-Cookie', c.output(header='').encode('ascii').strip())
            )
        # Initial response message.
        await send({
            'type': 'http.response.start',
            'status': response.status_code,
            'headers': response_headers,
        })
        # Streaming responses need to be pinned to their iterator.
        if response.streaming and not getattr(response, 'async_streaming', None):
            # Access `__iter__` and not `streaming_content` directly in case
            # it has been overridden in a subclass.
            for part in response:
                for chunk, _ in self.chunk_bytes(part):
                    await send({
                        'type': 'http.response.body',
                        'body': chunk,
                        # Ignore "more" as there may be more parts; instead,
                        # use an empty final closing message with False.
                        'more_body': True,
                    })
            # Final closing message.
            await send({'type': 'http.response.body'})
        elif getattr(response, 'async_streaming', None):
            # Access `__aiter__` and not `streaming_content` directly in case
            # it has been overridden in a subclass.
            async for part in response:
                for chunk, _ in self.chunk_bytes(part):
                    await send({
                        'type': 'http.response.body',
                        'body': chunk,
                        # Ignore "more" as there may be more parts; instead,
                        # use an empty final closing message with False.
                        'more_body': True,
                    })
            # Final closing message.
            await send({'type': 'http.response.body'})
        # Other responses just need chunking.
        else:
            # Yield chunks of response.
            for chunk, last in self.chunk_bytes(response.content):
                await send({
                    'type': 'http.response.body',
                    'body': chunk,
                    'more_body': not last,
                })
        await sync_to_async(response.close)()


def get_asgi_application():
    django.setup(set_prefix=False)
    return ASGIHandler()
