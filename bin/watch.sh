#!/usr/local/bin/zsh

MODULE='portal5'
BUNDLE=./$MODULE/bundle

(
    cd $BUNDLE &&
    nodemon \
    --watch . \
    --ignore ./public --ignore ./static \
    -e js,json,html,scss \
    --exec "python" ./bin/build.py
)
