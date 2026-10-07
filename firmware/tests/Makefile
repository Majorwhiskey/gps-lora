# SPDX-License-Identifier: Apache-2.0
# Host tests for the firmware's platform-independent code. Needs g++,
# OpenSSL headers (libssl-dev) and Python 3 with the cryptography package.
CXX ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Werror -O1
LIB := ../lib/gps-lora-core/src/gpslora
SRCS := firmware_test.cpp crypto_openssl.cpp $(LIB)/crypto.cpp $(LIB)/keys.cpp \
        $(LIB)/packet.cpp $(LIB)/seclog.cpp

test: firmware_test
	./firmware_test
	./firmware_test --vectors | python3 ../tools/gps_lora.py self-test

firmware_test: $(SRCS) $(wildcard $(LIB)/*.h)
	$(CXX) $(CXXFLAGS) -o $@ $(SRCS) -lcrypto

clean:
	rm -f firmware_test

.PHONY: test clean
