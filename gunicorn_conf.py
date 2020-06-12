import multiprocessing

bind = 'unix:/var/tmp/gunicorn.sock'
workers = 16
umask = 0o007
loglevel = 'warning'
errorlog = '/tmp/gunicorn.log'
capture_output = True
