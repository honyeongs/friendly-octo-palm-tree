# 웹 런타임과 자산 고지

이 앱은 원본 분석 코드를 브라우저에서 실행하기 위해 아래 구성요소를 사용합니다.
별도 구성요소의 원본 고지를 `licenses/`에 동봉하고 웹사이트에서도 제공합니다.

- **Pyodide 0.29.5**, MPL-2.0: [원본 소스](https://github.com/pyodide/pyodide/tree/0.29.5), [공식 core 배포](https://github.com/pyodide/pyodide/releases/tag/0.29.5). 런타임 파일은 수정하지 않았습니다.
- **CPython 3.13.2**와 포함 구성요소: [원본 소스](https://github.com/python/cpython/tree/v3.13.2), PSF 및 포함 구성요소 라이선스. `CPYTHON-LICENSE.txt`, `CPYTHON-THIRD-PARTY.rst`를 동봉합니다.
- 런타임 관련 Emscripten·LLVM/compiler-rt·musl·libffi·Expat·zlib 고지도 함께 제공합니다. 이는 각 구성요소의 소유권을 주장하거나 별도 라이선스로 바꾸는 것이 아닙니다.
- **Lucide / inherited Feather**: 기존 아이콘의 원본 ISC·MIT 고지를 동봉합니다. 앱용 PNG/ICO는 방패 도형에 배경·색상·크기만 조정한 파생 자산입니다.
- **NetSec의 dpkt 1.9.8**: 기존 BSD-3-Clause 원본 고지를 `third_party/dpkt`에서 웹 빌드의 `licenses/dpkt`로 복사합니다. 나머지 두 앱에는 dpkt가 포함되지 않습니다.
- Playwright는 개발·검증 도구이며 웹 런타임에 포함하지 않습니다. Sysmon 프로그램·악성코드·상용 탐지 규칙은 포함하지 않습니다.

고정 core 배포본 SHA-256:
`ab08aafc11a3c9a0fe73825eb2cec78bda9464348dd17414e7ec0132ef3451e8`.
이는 선택한 배포본을 동일하게 재현하기 위한 고정값이며 디지털 서명이나 공급자 진본성 보증은 아닙니다.
빌드의 `build-inventory.json`은 각 제공 파일의 SHA-256을 기록합니다.
완전한 SBOM·법률 자문·침해 부재 보증은 아닙니다.

자체 앱 코드와 별도 구성요소의 라이선스를 구분합니다. MPL을 자체 코드 전체의 라이선스로 지정하거나,
공개 GitHub 저장소라는 이유로 자체 코드에 상업적 재사용 허가를 자동 부여하지 않습니다.
