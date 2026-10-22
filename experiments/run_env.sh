# source 这个文件后再跑实验。国内镜像默认关闭，需要时 HEARSAY_USE_CN_MIRRORS=1
if [ "${HEARSAY_USE_CN_MIRRORS:-0}" = "1" ]; then
  export HF_ENDPOINT=https://hf-mirror.com
  export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
fi
export UV_HTTP_TIMEOUT=600
export OPENPRONOUNCE_TTS=kokoro
export OPENPRONOUNCE_DEVICE=cpu
export PYTORCH_ENABLE_MPS_FALLBACK=1
export TOKENIZERS_PARALLELISM=false
_lib=$(python -c "import espeakng_loader as e; print(e.get_library_path())" 2>/dev/null)
_data=$(python -c "import espeakng_loader as e; print(e.get_data_path())" 2>/dev/null)
[ -n "$_lib" ] && export PHONEMIZER_ESPEAK_LIBRARY="$_lib" && export ESPEAK_DATA_PATH="$_data"
