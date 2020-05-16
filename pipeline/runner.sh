#!/bin/bash
export PATH="$(pwd):$PATH"
cd beiwe-backend; python3 -m pipeline.run
