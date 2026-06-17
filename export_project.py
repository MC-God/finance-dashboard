import os

output_file = "project_context.txt"
# 제외할 폴더 및 파일 확장자 설정
ignore_dirs = {'.git', '__pycache__', '.pytest_cache', 'venv', 'env'}
ignore_exts = {'.pyc', '.png', '.jpg', '.jpeg', '.pdf', '.zip'}

# 🚨 보안상 반드시 제외해야 할 특정 파일명 (API 키, 인증서 등)
ignore_files = {'credentials.json', '.env', 'export_project.py', output_file}

with open(output_file, 'w', encoding='utf-8') as outfile:
    outfile.write("# [Project Full Context]\n")
    outfile.write("이 파일은 현재 헤지펀드 대시보드 프로젝트의 전체 디렉토리 및 파일 구조를 담고 있습니다.\n\n")
    
    for root, dirs, files in os.walk('.'):
        # 무시할 디렉토리 필터링
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        for file in files:
            # 출력 파일, 확장자 필터링, 그리고 민감한 보안 파일(credentials 등) 철저히 제외
            if file in ignore_files or any(file.endswith(ext) for ext in ignore_exts):
                continue
            
            file_path = os.path.join(root, file)
            
            outfile.write(f"{'='*60}\n")
            outfile.write(f"📁 File Path: {file_path}\n")
            outfile.write(f"{'='*60}\n")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as infile:
                    outfile.write(infile.read() + "\n\n")
            except Exception as e:
                outfile.write(f"(파일을 읽을 수 없습니다: {e})\n\n")

print(f"✅ 프로젝트 코드가 '{output_file}' 파일로 안전하게 병합되었습니다! (인증서 및 보안 파일 제외됨)")
