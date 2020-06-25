import json
import os
import sys
import time

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.http import HttpResponse, StreamingHttpResponse
from django.urls import path

settings.configure(
    DEBUG=(os.environ.get("DEBUG", "") == "1"),
    ALLOWED_HOSTS=["*"],
    ROOT_URLCONF=__name__,
    SECRET_KEY="super-secret-key",
    WSGI_APPLICATION=f"{__name__}.application",
)

application = get_wsgi_application()


def stream():
    counter = 100
    while counter > -1:
        i = json.dumps({"i": counter})
        content = f"event:i\ndata: {i}\n\n"
        counter -= 1
        yield content
        time.sleep(1)


def sse(request):
    response = StreamingHttpResponse(streaming_content=stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    return response


def index(request):
    return HttpResponse("""
    <h1>Countdown <span id="countdown"></span></h1>

    <script type="text/javascript">
        const evtSource = new EventSource("/sse/");
        const element = document.getElementById("countdown")
        evtSource.addEventListener("i", function(event) {
            i = JSON.parse(event.data).i
            if (i > 0) {
                element.innerText = i;
            } else {
                element.innerText = 'Blastoff!';
            }    
        });
    </script>
    """)


urlpatterns = [
    path("", index),
    path('sse/', sse)
]

if __name__ == "__main__":
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)