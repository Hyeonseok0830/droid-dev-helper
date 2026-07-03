# Droid Dev Helper

Droid Dev Helper는 Android 개발 및 테스트를 더욱 쉽고 빠르게 진행할 수 있도록 돕는 PyQt5 기반의 GUI 툴입니다. adb(Android Debug Bridge)와 scrcpy를 연동하여 기기 화면 제어와 로그캣 분석을 일체형으로 제공합니다.

## 주요 기능

- 화면 미러링: scrcpy를 백그라운드 스레드로 실행하여 딜레이 없는 화면 미러링 및 기기 제어를 제공합니다. 해상도, 비트레이트, FPS 등을 기호에 맞게 사전 설정할 수 있습니다.
- 실시간 Logcat 스트리머 및 하이라이트: 스레드 기반으로 실시간 로그캣을 읽어와 GUI 테이블에 표시합니다. 중요 로그 레벨(Verbose, Debug, Info, Warning, Error, Fatal)별 색상 강조와 함께, 특정 키워드를 기반으로 커스텀 하이라이팅을 제공합니다.
- 개발 편의 도구: 레이아웃 경계 표시 토글, 터치 피드백 표기 토글 등 개발자 옵션을 단 한 번의 클릭으로 활성화 및 비활성화할 수 있습니다. 스크린샷 캡처 및 시스템 개발자 옵션 페이지 즉시 실행 기능도 지원합니다.
- 기기 하드웨어 키 제어: Back, Home, Menu, 볼륨 제어, 전원 버튼, Recents 등 물리 하드웨어 키 이벤트를 원격으로 기기에 전송할 수 있습니다.
- 패키지 관리: 자주 사용하는 패키지명을 등록하여 캐시 데이터 초기화 및 앱 삭제 작업을 원격으로 수행합니다.

## 설치 및 요구사항

이 프로그램을 실행하기 위해서는 아래의 도구들이 호스트 PC에 설치되어 있어야 합니다.

1. Python 3.12 이상
2. adb (Android Debug Bridge)
3. scrcpy (화면 미러링용)

파이썬 의존성 설치:
pip install PyQt5

## 사용 방법

1. 소스 코드를 실행하거나 빌드된 실행 파일을 엽니다.
python app.py
2. 오른쪽 상단의 설정 아이콘을 눌러 본인 시스템에 설정된 adb 경로와 scrcpy 경로를 지정합니다.
3. Android 기기를 USB나 Wi-Fi를 통해 연결한 후, 장치 연결 상태 필터에서 대상을 선택하여 사용을 시작합니다.

## 로컬 빌드 방법

PyInstaller를 통해 단일 파일 실행 파일로 빌드하려면 아래 명령어를 사용하십시오.

- 윈도우 환경:
pyinstaller --onefile --noconsole --name="droid-dev-helper" --add-data "droid-dev-helper.png;." --icon="droid-dev-helper.ico" app.py

- 리눅스 환경:
pyinstaller --onefile --noconsole --name="droid-dev-helper" --add-data "droid-dev-helper.png:." app.py
