# grader/judge_backend.py

import sys
import json
import subprocess
import os
import pathlib
import tempfile
from typing import List, Dict

# ==============================================================================
# --- CẤU HÌNH ĐƯỜNG DẪN TRÌNH BIÊN DỊCH ---
# Vui lòng thay đổi các đường dẫn này cho phù hợp với máy của bạn.
# ==============================================================================

# 1. Trỏ đến thư mục 'bin' của JDK (chứa javac.exe và java.exe)
# Ví dụ: r"C:\Program Files\Java\jdk-21\bin"
JDK_BIN_PATH = pathlib.Path(r"D:\jdk-23_windows-x64_bin\jdk-23.0.1\bin")

# 2. Trỏ đến thư mục 'bin' của trình biên dịch C++ (ví dụ: MinGW-w64)
# Ví dụ: r"C:\msys64\mingw64\bin"
# Nếu bạn đã thêm g++ vào PATH hệ thống, có thể để trống: CPP_COMPILER_DIR = None
CPP_COMPILER_DIR = pathlib.Path(r"C:\msys64\mingw64\bin")
# === CÁC HÀM CHẤM BÀI CHO TỪNG NGÔN NGỮ ===

def judge_python(user_code_path: str, test_case: Dict) -> Dict:
    """Chấm một test case cho code Python."""
    stdin_data = test_case.get("stdin", "")
    expected_stdout = test_case.get("expected_stdout", "")
    case_id = test_case.get("id", "N/A")

    try:
        process = subprocess.run(
            [sys.executable, user_code_path],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        actual_stdout = process.stdout.strip()

        if process.returncode != 0:
            return {"test_case_id": case_id, "status": "RUNTIME_ERROR", "detail": process.stderr.strip()}

        if actual_stdout == expected_stdout.strip():
            return {"test_case_id": case_id, "status": "ACCEPTED", "output": actual_stdout}
        else:
            return {"test_case_id": case_id, "status": "WRONG_ANSWER", "output": actual_stdout,
                    "expected": expected_stdout}

    except subprocess.TimeoutExpired:
        return {"test_case_id": case_id, "status": "TIME_LIMIT_EXCEEDED"}
    except Exception as e:
        return {"test_case_id": case_id, "status": "GRADER_ERROR", "detail": str(e)}


def judge_cpp(user_code_path: str, test_case: Dict) -> Dict:
    """Biên dịch và chấm một test case cho code C++."""
    source_path = pathlib.Path(user_code_path)
    case_id = test_case.get("id", "N/A")

    # Tạo file thực thi trong một thư mục tạm thời để tránh xung đột
    with tempfile.TemporaryDirectory() as temp_dir:
        executable_name = "solution.exe" if sys.platform == "win32" else "solution"
        executable_path = pathlib.Path(temp_dir) / executable_name

        # --- Bước 1: Biên dịch ---
        compile_process = subprocess.run(
            ["g++", str(source_path), "-o", str(executable_path), "-std=c++17"],
            capture_output=True,
            text=True
        )

        if compile_process.returncode != 0:
            return {"test_case_id": case_id, "status": "COMPILATION_ERROR", "detail": compile_process.stderr.strip()}

        # --- Bước 2: Thực thi ---
        stdin_data = test_case.get("stdin", "")
        expected_stdout = test_case.get("expected_stdout", "")

        try:
            execute_process = subprocess.run(
                [str(executable_path)],
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            actual_stdout = execute_process.stdout.strip()

            if execute_process.returncode != 0:
                return {"test_case_id": case_id, "status": "RUNTIME_ERROR", "detail": execute_process.stderr.strip()}

            if actual_stdout == expected_stdout.strip():
                return {"test_case_id": case_id, "status": "ACCEPTED", "output": actual_stdout}
            else:
                return {"test_case_id": case_id, "status": "WRONG_ANSWER", "output": actual_stdout,
                        "expected": expected_stdout}

        except subprocess.TimeoutExpired:
            return {"test_case_id": case_id, "status": "TIME_LIMIT_EXCEEDED"}
        except Exception as e:
            return {"test_case_id": case_id, "status": "GRADER_ERROR", "detail": str(e)}


def judge_java(user_code_path: str, test_case: Dict) -> Dict:
    """Biên dịch và chấm một test case cho code Java."""
    original_source_path = pathlib.Path(user_code_path)
    case_id = test_case.get("id", "N/A")

    # SỬA LỖI: Tạo file Main.java để biên dịch
    # Java yêu cầu tên file phải trùng với tên class public.
    # Boilerplate của chúng ta dùng `public class Main`.
    main_class_name = "Main"
    # Tạo file Main.java trong cùng thư mục với file tạm
    correct_source_path = original_source_path.parent / f"{main_class_name}.java"
    class_file_path = correct_source_path.with_suffix(".class")

    try:
        # Đọc nội dung từ file tạm và ghi vào file Main.java
        with open(original_source_path, 'r', encoding='utf-8') as f_in:
            code_content = f_in.read()
        with open(correct_source_path, 'w', encoding='utf-8') as f_out:
            f_out.write(code_content)

    except IOError as e:
        return {"test_case_id": case_id, "status": "GRADER_ERROR", "detail": f"Lỗi khi xử lý file code: {e}"}

    javac_path = JDK_BIN_PATH / "javac.exe"
    java_path = JDK_BIN_PATH / "java.exe"

    if not javac_path.exists() or not java_path.exists():
        return {"test_case_id": case_id, "status": "GRADER_ERROR",
                "detail": f"Không tìm thấy trình biên dịch Java tại: {JDK_BIN_PATH}"}

    # --- Bước 1: Biên dịch file Main.java ---
    compile_process = subprocess.run(
        [str(javac_path), str(correct_source_path)],  # Compile the correctly named file
        capture_output=True,
        text=True,
        encoding='utf-8',
        cwd=correct_source_path.parent
    )

    if compile_process.returncode != 0:
        if correct_source_path.exists(): os.remove(correct_source_path)
        return {"test_case_id": case_id, "status": "COMPILATION_ERROR", "detail": compile_process.stderr.strip()}

    # --- Bước 2: Thực thi ---
    stdin_data = test_case.get("stdin", "")
    expected_stdout = test_case.get("expected_stdout", "")

    try:
        execute_process = subprocess.run(
            [str(java_path), main_class_name],  # Run 'java Main'
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            encoding='utf-8',
            cwd=correct_source_path.parent
        )
        actual_stdout = execute_process.stdout.strip()

        if execute_process.returncode != 0:
            return {"test_case_id": case_id, "status": "RUNTIME_ERROR", "detail": execute_process.stderr.strip()}

        if actual_stdout == expected_stdout.strip():
            return {"test_case_id": case_id, "status": "ACCEPTED", "output": actual_stdout}
        else:
            return {"test_case_id": case_id, "status": "WRONG_ANSWER", "output": actual_stdout,
                    "expected": expected_stdout}

    except subprocess.TimeoutExpired:
        return {"test_case_id": case_id, "status": "TIME_LIMIT_EXCEEDED"}
    except Exception as e:
        return {"test_case_id": case_id, "status": "GRADER_ERROR", "detail": str(e)}
    finally:
        # Dọn dẹp file .class và file Main.java
        if class_file_path.exists():
            os.remove(class_file_path)
        if correct_source_path.exists():
            os.remove(correct_source_path)


# === HÀM CHÍNH ĐIỀU PHỐI ===

def run_backend_grader(user_code_path: str, test_cases_json: str) -> List[Dict]:
    """
    Điều phối việc chấm bài dựa trên đuôi file.
    """
    try:
        test_cases = json.loads(test_cases_json)
    except json.JSONDecodeError:
        return [{"status": "GRADER_ERROR", "detail": "Invalid test cases JSON format."}]

    # Xác định ngôn ngữ dựa trên đuôi file
    file_extension = pathlib.Path(user_code_path).suffix

    judge_function = None
    if file_extension == '.py':
        judge_function = judge_python
    elif file_extension == '.cpp':
        judge_function = judge_cpp
    elif file_extension == '.java':
        judge_function = judge_java
    else:
        return [{"status": "GRADER_ERROR", "detail": f"Unsupported file type: {file_extension}"}]

    results = []
    for case in test_cases:
        result = judge_function(user_code_path, case)
        results.append(result)
        # Nếu gặp lỗi nghiêm trọng (biên dịch, runtime), có thể dừng sớm
        if result["status"] in ["COMPILATION_ERROR", "GRADER_ERROR"]:
            # Điền nốt các test case còn lại với cùng lỗi để người dùng biết
            remaining_cases = len(test_cases) - len(results)
            for _ in range(remaining_cases):
                results.append(result)
            break

    return results


if __name__ == "__main__":
    if len(sys.argv) != 3:
        usage_error = [
            {"status": "GRADER_ERROR", "detail": "Usage: python judge_backend.py <user_code_path> <test_cases_json>"}]
        print(json.dumps(usage_error))
        sys.exit(1)

    user_code_path_arg = sys.argv[1]
    test_cases_json_arg = sys.argv[2]

    final_results = run_backend_grader(user_code_path_arg, test_cases_json_arg)

    print(json.dumps(final_results, indent=4))
