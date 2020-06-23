from django.http import HttpResponse


class AysncStreamingHttpResponse(HttpResponse):
    async_streaming = True
    streaming = True

    def __init__(self, streaming_content=(), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.streaming_content = (self.make_bytes(chunk) async for chunk in streaming_content)

    def __aiter__(self):
        return self.streaming_content

    async def getvalue(self):
        return b''.join(chunk async for chunk in self.streaming_content)