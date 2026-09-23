"""Single-process application entrypoint; never executes generated code."""
import os
import uvicorn
from .config import settings
if __name__ == '__main__':
    uvicorn.run('app.main:app', host=os.getenv('BIND_HOST','127.0.0.1'), port=int(os.getenv('PORT','8000')), workers=1, log_level='warning')
