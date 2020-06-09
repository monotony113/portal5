import multiprocessing

bind = 'unix:/var/tmp/gunicorn.sock'
workers = 16
umask = 0o007
loglevel = 'debug'
errorlog = '/tmp/gunicorn.log'
capture_output = True
