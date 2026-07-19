<?php

interface Shape {
    public function area(): float;
}

trait Loggable {
    public function log() {}
}

enum Status {
    case Active;
}

class Service {
    public function run() {}
}

function topLevel() {}
