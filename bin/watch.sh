#!/usr/local/bin/zsh

MODULE='portalx'
BUNDLE=./$MODULE/bundle

(
    cd $BUNDLE &&
    nodemon \
    --watch . \
    --ignore ./public --ignore ./static \
    -e js,json,html,scss \
    --exec "python" ./bin/build.py
)
