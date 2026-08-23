"""테스트가 어디서 실행되든 스킬의 scripts/ 를 import 경로에 넣는다(설치 불요)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
