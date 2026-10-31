# PF3 Converter v1.1 — sRGB CUBE 출력 안내

## 각 출력 파일의 용도

- **Photoshop CUBE**: sRGB 문서에서 Photoshop의 색상 검색(Color Lookup) 조정 레이어에 사용합니다.
- **LUMIX CUBE**: REAL TIME LUT가 지원되는 파나소닉 LUMIX 카메라에서 사용합니다. LUT의 기준 Photo Style을 선택합니다.
- **XMP**: Adobe Lightroom / Camera Raw용 컬러 프로파일입니다.
- **PF3**: Canon Picture Style. v1.1에서는 변환 모듈을 변경하지 않았습니다.

**일반 CUBE와 LUMIX CUBE를 동일 강도로 저장하면 RGB 테이블 값이 완전히 동일합니다.**
두 파일의 차이는 LUMIX 전용 `#LUMIXPHOTOSTYLE` 메타데이터의 유무입니다.
이 메타데이터가 실제 카메라의 LUT 적용 이전 Photo Style을 선택하므로, 카메라에서
Photoshop과 다른 렌더링 결과가 생길 수 있습니다.

## 제공한 `classic negative_by.BB.xmp`의 특성

이 XMP는 내장 3D LUT가 없는 **Lightroom 현상 프리셋**입니다. 노출(+0.55),
하이라이트(-22), 섀도(+15), 매개변수/포인트 톤 커브, HSL, 생동감(+9) 및
**Adobe Color 참조**를 포함합니다. Adobe Color 카메라 프로파일 자체는 들어 있지 않습니다.
따라서 XMP만을 읽어도 Adobe 현상 엔진과 같은 색을 생성할 수 있는 것이 아닙니다.
현재 내장된 자동 근사 변환은 더 이상 PF3 코드와 함께 바뀌지 않습니다.

## 비교 시 주의사항

Photoshop의 sRGB 문서에서 같은 강도의 CUBE를 적용하면 동일한 RGB 변환값을 갖습니다.
Lightroom의 현상 프리셋은 Adobe Color 및 RAW 현상 파이프라인을 참조할 수 있으므로,
sRGB 설정만 같다고 원본 XMP와 CUBE의 렌더링까지 같아지는 것은 아닙니다.

## 테스트

사용자 XMP로 **100% 및 50%** CUBE 두 개를 각각 출력해 RGB 테이블을
비교했습니다. 두 강도 모두 **최대·평균 차이 0 / 255**로 확인했습니다.
이 테스트는 CUBE 형식 자체의 일관성 검증이며, Adobe Lightroom / Photoshop
실제 프로그램에서의 렌더링 오차 측정은 아닙니다.
