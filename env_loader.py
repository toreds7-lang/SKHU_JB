"""env.txt 로더 — 경량 모듈, 외부 의존성 없음"""
import os


def load_env_txt(path: str = "env.txt") -> dict[str, str]:
    """env.txt 파일에서 KEY=VALUE 형태의 설정을 읽어 os.environ에 반영."""
    env_vars = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip()
                    env_vars[key] = value
                    os.environ.setdefault(key, value)
    return env_vars
