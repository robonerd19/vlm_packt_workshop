ARG CUDA_VERSION=12.8.1
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04 AS build
ARG LLAMA_COMMIT=0504396140d1c882f5f6ee34466a42db7ae90114
ARG CUDA_ARCHITECTURES=89
ARG BUILD_JOBS=2
RUN apt-get update && apt-get install -y --no-install-recommends \
    git cmake g++ make ca-certificates libcurl4-openssl-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN git init && git remote add origin https://github.com/ggml-org/llama.cpp.git && \
    git fetch --depth 1 origin ${LLAMA_COMMIT} && git checkout FETCH_HEAD
RUN cmake -S . -B out -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
    -DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_AVX512=OFF \
    -DGGML_CUDA=ON -DGGML_VULKAN=OFF -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHITECTURES}" \
    -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON && \
    cmake --build out --target llama-server -j${BUILD_JOBS}
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu24.04
ARG CUDA_ARCHITECTURES=89
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl libcurl4t64 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --from=build /build/out/bin/llama-server /usr/local/bin/llama-server
COPY docker/inference_entrypoint.sh /inference_entrypoint.sh
RUN chmod +x /inference_entrypoint.sh
LABEL org.vlm-workshop.inference.device="gpu" \
      org.vlm-workshop.cuda.architectures="${CUDA_ARCHITECTURES}"
ENTRYPOINT ["/inference_entrypoint.sh"]
CMD ["gpu"]
