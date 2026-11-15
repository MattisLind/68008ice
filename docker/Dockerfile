FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake curl git ninja-build python3 \
    gcc-arm-none-eabi libnewlib-arm-none-eabi libstdc++-arm-none-eabi-newlib gdb-multiarch \
    libusb-1.0-0 usbutils \
    && rm -rf /var/lib/apt/lists/*

# Pico SDK 2.3.1. Pin the source as well as the release name.
RUN git clone --depth 1 --branch 2.3.1 https://github.com/raspberrypi/pico-sdk.git /opt/pico-sdk \
    && test "$(git -C /opt/pico-sdk rev-parse HEAD)" = 079c6f39023649b154152db30f1d781e884879bc \
    && git -C /opt/pico-sdk submodule update --init --depth 1 lib/tinyusb

# Raspberry Pi's official binaries include RP2350 support. Both native Linux
# architectures are supported; macOS uses the matching host OpenOCD as a bridge.
RUN set -eu; case "$(dpkg --print-architecture)" in \
      arm64) arch=aarch64; \
        pico_sha=8cce5579c92e77c0439f34d4f49d37b1dc7d1e7c455233398f2e7b49599f67aa; \
        ocd_sha=7b2d56d74ca27485bfc5a72fd59ac6684877a41e09abddcc18475cc9291adff5 ;; \
      amd64) arch=x86_64; \
        pico_sha=878a1a1e7d8336b8be60300c7218f366d9790c0d3a211b181d6d172e80b1248e; \
        ocd_sha=7b2ad4bb310356c7e50c17d0a813f7f803765ea4a0610a2191909767835f3b0d ;; \
      *) exit 1 ;; esac; \
    base=https://github.com/raspberrypi/pico-sdk-tools/releases/download/v2.3.1-0; \
    curl -fL "$base/picotool-2.3.1-$arch-lin.tar.gz" -o /tmp/picotool.tar.gz; \
    echo "$pico_sha  /tmp/picotool.tar.gz" | sha256sum -c -; \
    mkdir -p /opt/picotool; tar -xf /tmp/picotool.tar.gz -C /opt/picotool; \
    curl -fL "$base/openocd-0.12.0%2Bdev-$arch-lin.tar.gz" -o /tmp/openocd.tar.gz; \
    echo "$ocd_sha  /tmp/openocd.tar.gz" | sha256sum -c -; \
    mkdir -p /opt/openocd; tar -xf /tmp/openocd.tar.gz -C /opt/openocd; \
    rm /tmp/picotool.tar.gz /tmp/openocd.tar.gz

ENV PICO_SDK_PATH=/opt/pico-sdk
ENV OPENOCD_SCRIPTS=/opt/openocd/scripts
ENV PATH=/opt/picotool/picotool:/opt/picotool:/opt/openocd:${PATH}
RUN apt-get update && apt-get install -y --no-install-recommends \
    libftdi1-2 libhidapi-hidraw0 \
    && rm -rf /var/lib/apt/lists/* \
    && openocd --version && picotool version
WORKDIR /work
CMD ["bash"]
