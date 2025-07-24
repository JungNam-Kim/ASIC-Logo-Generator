# dependency: gdspy, PIL, numpy, json, os
# pip install gdspy pillow numpy
# This script generates GDS and LEF files from a bitmap image of a logo.
"""
Logo to GDS/LEF Generator

This tool converts bitmap images (logos) into GDS (GDSII) and LEF (Library Exchange Format) files
that can be used in integrated circuit design workflows. The tool supports multi-layer metal
stacks with via interconnections.
If PDK supports dummy metal exclusion layer, it can also generate exclusion layers.

Author: Jung Nam Kim
License: MIT
"""
import gdspy
from PIL import Image
import numpy as np
import json
import os
import argparse

def parse_layer_constraints(json_path):
    with open(json_path, 'r') as f:
        return json.load(f)


def threshold_image(image_path, threshold=128):
    """Convert grayscale image to binary using threshold."""
    image = Image.open(image_path).convert('L')
    binary_image = image.point(lambda p: 0 if p < threshold else 255, '1')
    return binary_image

def bitmap_to_stacked_logo(
    image_path,
    constraint_json_path,
    output_gds,
    pixel_size_um=1.0,
    threshold_value=128
):
    constraints = parse_layer_constraints(constraint_json_path)

    metal_layers = sorted(
        [k for k in constraints if k.startswith("metal")], key=lambda x: int(x[5:])
    )
    via_layers = sorted(
        [k for k in constraints if k.startswith("via")], key=lambda x: int(x[3:])
    )
    logo_layer_info = constraints.get("logo", {"layer": 100, "datatype": 0})

    # DMxEXCL 레이어만 추출 (예: DM1EXCL, DM2EXCL, ...)
    DMxEXCL_layer_info = sorted(
        [k for k in constraints if k.startswith("DM") and k.endswith("EXCL") and k[2:-4].isdigit()],
        key=lambda x: int(x[2:-4])
    )

    image = threshold_image(image_path, threshold=threshold_value)
    width, height = image.size
    pixels = np.array(image, dtype=np.uint8)
    cell = gdspy.Cell("LOGO")
    filled = np.zeros_like(pixels, dtype=bool)

    # 2x2 convolution to find diagonal patterns
    # 먼저, 메탈 레이어 중 가장 큰 min_width를 구함
    max_min_width = 0.0
    for metal in metal_layers:
        spec = constraints[metal]
        min_width = spec.get("min_width", 0.0)
        min_area = spec.get("min_area", 0.0)
        if pixel_size_um < min_width or (pixel_size_um**2) < min_area:
            continue
        if min_width > max_min_width:
            max_min_width = min_width

    for y in range(height - 1):
        for x in range(width - 1):
            block = pixels[y:y+2, x:x+2]
            # Pattern 1: [1,0],[0,1] (↘)
            if (block[0, 0] == 0 and block[1, 1] == 0 and block[0, 1] != 0 and block[1, 0] != 0):
                center_x = (x + 1) * pixel_size_um
                center_y = (height - (y + 1)) * pixel_size_um
                for m_idx, metal in enumerate(metal_layers):
                    spec = constraints[metal]
                    min_area = spec.get("min_area", 0.0)
                    # 모든 메탈에 대해 가장 큰 width로 fill
                    if max_min_width > pixel_size_um or (max_min_width**2) < min_area:
                        continue
                    half = max_min_width / 2.0
                    rect = gdspy.Rectangle(
                        (center_x - half, center_y - half),
                        (center_x + half, center_y + half),
                        layer=spec["layer"], datatype=spec["datatype"]
                    )
                    cell.add(rect)
            # Pattern 2: [0,1],[1,0] (↗)
            elif (block[0, 1] == 0 and block[1, 0] == 0 and block[0, 0] != 0 and block[1, 1] != 0):
                center_x = (x + 1) * pixel_size_um
                center_y = (height - (y + 1)) * pixel_size_um
                for m_idx, metal in enumerate(metal_layers):
                    spec = constraints[metal]
                    min_area = spec.get("min_area", 0.0)
                    if max_min_width > pixel_size_um or (max_min_width**2) < min_area:
                        continue
                    half = max_min_width / 2.0
                    rect = gdspy.Rectangle(
                        (center_x - half, center_y - half),
                        (center_x + half, center_y + half),
                        layer=spec["layer"], datatype=spec["datatype"]
                    )
                    cell.add(rect)

    # 일반적인 픽셀(검정) 메탈 채우기
    for y in range(height):
        for x in range(width):
            if pixels[y, x] == 0:
                px0 = x * pixel_size_um
                py0 = (height - 1 - y) * pixel_size_um
                px1 = px0 + pixel_size_um
                py1 = py0 + pixel_size_um
                for m_idx, metal in enumerate(metal_layers):
                    spec = constraints[metal]
                    min_width = spec.get("min_width", 0.0)
                    min_area = spec.get("min_area", 0.0)
                    if pixel_size_um < min_width or (pixel_size_um**2) < min_area:
                        continue
                    rect = gdspy.Rectangle(
                        (px0, py0), (px1, py1),
                        layer=spec["layer"], datatype=spec["datatype"]
                    )
                    cell.add(rect)
                    # VIA 추가
                    if m_idx < len(via_layers):
                        via = via_layers[m_idx]
                        via_spec = constraints[via]
                        via_w = via_spec.get("width", 0.1)
                        via_h = via_spec.get("height", 0.1)
                        via_spacing = via_spec.get("spacing", via_w)
                        total_via_w = via_w + via_spacing
                        total_via_h = via_h + via_spacing
                        num_x = int(pixel_size_um // total_via_w)
                        num_y = int(pixel_size_um // total_via_h)
                        arr_w = num_x * total_via_w - via_spacing if num_x > 0 else 0
                        arr_h = num_y * total_via_h - via_spacing if num_y > 0 else 0
                        arr_x0 = px0 + (pixel_size_um - arr_w) / 2.0
                        arr_y0 = py0 + (pixel_size_um - arr_h) / 2.0
                        for i in range(num_x):
                            for j in range(num_y):
                                vx0 = arr_x0 + i * total_via_w
                                vy0 = arr_y0 + j * total_via_h
                                if vx0 + via_w <= px1 and vy0 + via_h <= py1:
                                    via_rect = gdspy.Rectangle(
                                        (vx0, vy0), (vx0 + via_w, vy0 + via_h),
                                        layer=via_spec["layer"], datatype=via_spec["datatype"]
                                    )
                                    cell.add(via_rect)

    # 로고 외곽선 추가
    x0 = 0
    y0 = 0
    x1 = width * pixel_size_um
    y1 = height * pixel_size_um
    logo_rect = gdspy.Rectangle(
        (x0, y0), (x1, y1),
        layer=logo_layer_info["layer"],
        datatype=logo_layer_info["datatype"]
    )
    cell.add(logo_rect)
    
    # DMxEXCL 레이어에 대한 처리
    for layer in DMxEXCL_layer_info:
        spec = constraints[layer]
        min_width = spec.get("min_width", 0.0)
        min_area = spec.get("min_area", 0.0)
        if pixel_size_um < min_width or (pixel_size_um**2) < min_area:
            continue
        half = pixel_size_um / 2.0
        rect = gdspy.Rectangle(
            (0, 0), (width * pixel_size_um, height * pixel_size_um),
            layer=spec["layer"], datatype=spec["datatype"]
        )
        cell.add(rect)

    lib = gdspy.GdsLibrary()
    lib.add(cell)
    lib.write_gds(output_gds)
    return f"GDS file generated: {output_gds}"


def generate_lef_from_logo(
    image_path,
    constraint_json_path,
    output_lef,
    macro_name="LOGO_CELL",
    pixel_size_um=1.0,
    threshold_value=128,
    units=1000  # LEF units (typically 1000 = 1um)
):
    """
    비트맵 이미지로부터 LEF (Library Exchange Format) 파일을 생성합니다.
    
    Args:
        image_path: 입력 비트맵 이미지 경로
        constraint_json_path: 레이어 제약조건 JSON 파일 경로
        output_lef: 출력 LEF 파일 경로
        macro_name: 매크로 셀 이름
        pixel_size_um: 픽셀 크기 (마이크로미터)
        threshold_value: 이진화 임계값
        units: LEF 단위 (1000 = 1마이크로미터)
    """
    constraints = parse_layer_constraints(constraint_json_path)
    
    # 메탈 레이어 및 VIA 레이어 정렬
    metal_layers = sorted(
        [k for k in constraints if k.startswith("metal")], key=lambda x: int(x[5:])
    )
    via_layers = sorted(
        [k for k in constraints if k.startswith("via")], key=lambda x: int(x[3:])
    )
    
    # 이미지 처리
    image = threshold_image(image_path, threshold=threshold_value)
    width, height = image.size
    pixels = np.array(image, dtype=np.uint8)
    
    # LEF 단위로 변환 (마이크로미터 -> LEF 단위)
    width_lef = width * pixel_size_um * units
    height_lef = height * pixel_size_um * units
    
    # LEF 파일 내용 생성
    lef_content = []
    
    # LEF 헤더
    lef_content.append("VERSION 5.7 ;")
    lef_content.append("NAMESCASESENSITIVE ON ;")
    lef_content.append("BUSBITCHARS \"[]\" ;")
    lef_content.append("DIVIDERCHAR \"/\" ;")
    lef_content.append("")
    
    # 매크로 정의 시작
    lef_content.append(f"MACRO {macro_name}")
    lef_content.append("    CLASS BLOCK ;")
    lef_content.append(f"    FOREIGN {macro_name} 0 0 ;")
    lef_content.append("    ORIGIN 0 0 ;")
    lef_content.append(f"    SIZE {width_lef/1000:.0f} BY {height_lef/1000:.0f} ;")
    lef_content.append("    SYMMETRY X Y R90 ;")
    lef_content.append("")
    
    # 매크로 정의 종료
    lef_content.append(f"END {macro_name}")
    lef_content.append("")
    lef_content.append("END LIBRARY")
    
    # LEF 파일 작성
    with open(output_lef, 'w') as f:
        f.write('\n'.join(lef_content))
    
    return f"LEF file generated: {output_lef}"


def generate_logo_files(
    image_path,
    constraint_json_path,
    output_gds,
    output_lef=None,
    macro_name="LOGO_CELL",
    pixel_size_um=1.0,
    threshold_value=128
):
    """
    비트맵 이미지로부터 GDS와 LEF 파일을 모두 생성합니다.
    
    Args:
        image_path: 입력 비트맵 이미지 경로
        constraint_json_path: 레이어 제약조건 JSON 파일 경로
        output_gds: 출력 GDS 파일 경로
        output_lef: 출력 LEF 파일 경로 (None이면 생성하지 않음)
        macro_name: 매크로 셀 이름
        pixel_size_um: 픽셀 크기 (마이크로미터)
        threshold_value: 이진화 임계값
    """
    results = []
    
    # GDS 파일 생성
    gds_result = bitmap_to_stacked_logo(
        image_path=image_path,
        constraint_json_path=constraint_json_path,
        output_gds=output_gds,
        pixel_size_um=pixel_size_um,
        threshold_value=threshold_value
    )
    results.append(gds_result)
    
    # LEF 파일 생성 (요청된 경우)
    if output_lef:
        lef_result = generate_lef_from_logo(
            image_path=image_path,
            constraint_json_path=constraint_json_path,
            output_lef=output_lef,
            macro_name=macro_name,
            pixel_size_um=pixel_size_um,
            threshold_value=threshold_value
        )
        results.append(lef_result)
    
    return results


if "__main__" == __name__:
    argparser = argparse.ArgumentParser(description="Generate GDS and LEF files from a logo bitmap image.")
    argparser.add_argument("--image", type=str, required=True, help="Path to the bitmap image file (logo).")
    argparser.add_argument("--constraints", type=str, required=True, help="Path to the JSON file with layer constraints.")
    argparser.add_argument("--output_dir", type=str, required=True, help="Path to the output GDS file.")
    argparser.add_argument("--macro_name", type=str, default="LOGO_CELL", help="Name of the macro cell in the LEF file.")
    argparser.add_argument("--pixel_size_um", type=float, default=1.0, help="Pixel size in micrometers.")
    argparser.add_argument("--threshold_value", type=int, default=128, help="Threshold value for binarization of the image.")

    args = argparser.parse_args()
    InputImage = args.image
    ConstraintFile = args.constraints
    OutputDir = args.output_dir

    if not os.path.exists(InputImage):
        raise FileNotFoundError(f"Input image file not found: {InputImage}")
    if not os.path.exists(ConstraintFile):
        raise FileNotFoundError(f"Constraint JSON file not found: {ConstraintFile}")
    if not os.path.exists(OutputDir):
        os.mkdir(OutputDir)
        
    results = generate_logo_files(
        image_path=InputImage,
        constraint_json_path=ConstraintFile,
        output_gds=os.path.join(OutputDir, "logo.gds"),
        output_lef=os.path.join(OutputDir, "logo.lef"),
        macro_name="LOGO_CELL",
        pixel_size_um=args.pixel_size_um,
        threshold_value=args.threshold_value
    )
    
    for result in results:
        print(result)