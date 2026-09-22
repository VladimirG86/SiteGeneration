"""Абстракция хранения: локально (SITES_DIR) или S3-совместимо.

Если задан SITEGEN_S3_BUCKET — ассеты и json дублируются в S3
через boto3 (опционально). Без boto3 или без бакета — чисто локально.
Позволяет в проде переключиться на S3 без правки generator/images.

ENV:
  SITEGEN_S3_BUCKET
  SITEGEN_S3_REGION (default eu-central-1)
  SITEGEN_S3_ENDPOINT (для Yandex/Selectel/MinIO)
  SITEGEN_S3_ACCESS_KEY / SITEGEN_S3_SECRET_KEY
  (или стандартные AWS_*)

Использование: storage.save_bytes(key, data), storage.load_bytes(key)
где key = "sites/<job>.json" или "assets/<job>/hero.webp"
"""
import os
import threading

SITES_DIR = os.environ.get("SITEGEN_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "sites")
S3_BUCKET = os.environ.get("SITEGEN_S3_BUCKET", "").strip()
S3_REGION = os.environ.get("SITEGEN_S3_REGION", "eu-central-1").strip() or "eu-central-1"
S3_ENDPOINT = os.environ.get("SITEGEN_S3_ENDPOINT", "").strip()
S3_ACCESS = os.environ.get("SITEGEN_S3_ACCESS_KEY", "").strip() or os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
S3_SECRET = os.environ.get("SITEGEN_S3_SECRET_KEY", "").strip() or os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()

_s3_client = None
_s3_lock = threading.Lock()
_s3_enabled = False

def _init_s3():
    global _s3_client, _s3_enabled
    if not S3_BUCKET:
        return None
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
    except ImportError:
        print("[STORAGE] boto3 не установлен — S3 отключён, работаем локально")
        return None
    kwargs = {"region_name": S3_REGION}
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
    if S3_ACCESS and S3_SECRET:
        kwargs["aws_access_key_id"] = S3_ACCESS
        kwargs["aws_secret_access_key"] = S3_SECRET
    try:
        client = boto3.client("s3", config=Config(s3={"addressing_style": "virtual"}), **kwargs)
        # лёгкая проверка
        client.head_bucket(Bucket=S3_BUCKET)
        _s3_enabled = True
        print(f"[STORAGE] S3 подключён: s3://{S3_BUCKET} ({S3_ENDPOINT or S3_REGION})")
        return client
    except Exception as e:  # noqa: BLE001
        print(f"[STORAGE] S3 не доступен ({e}) — fallback на локаль")
        return None

def _get_s3():
    global _s3_client
    with _s3_lock:
        if _s3_client is None and S3_BUCKET:
            _s3_client = _init_s3()
        return _s3_client

def is_s3() -> bool:
    return S3_BUCKET != "" and _get_s3() is not None

def _key_to_local(key: str) -> str:
    # key like sites/abc.json or assets/abc/hero.webp
    # SITES_DIR is .../sites, so we need base
    base = os.path.dirname(SITES_DIR)
    return os.path.join(base, key)

def save_bytes(key: str, data: bytes):
    # всегда локально
    p = _key_to_local(key)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    # дубль в S3 асинхронно (пока синхронно, но быстро)
    s3 = _get_s3()
    if s3:
        try:
            s3.put_object(Bucket=S3_BUCKET, Key=key, Body=data)
        except Exception as e:  # noqa: BLE001
            print(f"[STORAGE] S3 put {key} failed: {e}")

def load_bytes(key: str) -> bytes | None:
    s3 = _get_s3()
    if s3:
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            return obj["Body"].read()
        except Exception:
            pass
    p = _key_to_local(key)
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f.read()
    return None

def exists(key: str) -> bool:
    s3 = _get_s3()
    if s3:
        try:
            s3.head_object(Bucket=S3_BUCKET, Key=key)
            return True
        except Exception:
            pass
    return os.path.exists(_key_to_local(key))

def delete(key: str):
    p = _key_to_local(key)
    try:
        os.remove(p)
    except OSError:
        pass
    s3 = _get_s3()
    if s3:
        try:
            s3.delete_object(Bucket=S3_BUCKET, Key=key)
        except Exception:
            pass
