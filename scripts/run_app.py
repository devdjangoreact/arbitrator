#!/usr/bin/env python3
import sys
import os
import subprocess
import platform
import time
from pathlib import Path
import uvicorn

# Ensure the root directory is in the Python path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))
sys.path.insert(0, str(root_dir)) # Add root so 'main' can be resolved

from arbitrator.config.settings import Settings

def kill_process_on_port(port: int):
    """Kills any process currently listening on the given port."""
    print(f"Checking for existing processes on port {port}...")
    try:
        if platform.system() == "Windows":
            # Find PID using netstat
            cmd = f'netstat -ano | findstr LISTENING | findstr :{port}'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.stdout:
                killed_any = False
                for line in result.stdout.strip().split('\n'):
                    parts = line.strip().split()
                    # Example line: TCP  127.0.0.1:8000  0.0.0.0:0  LISTENING  1234
                    if len(parts) >= 5 and parts[3] == "LISTENING" and str(port) in parts[1]:
                        pid = parts[4]
                        print(f"Killing process {pid} on port {port}...")
                        subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                        killed_any = True
                if killed_any:
                    time.sleep(1) # Give OS a moment to free the port
        else:
            # Unix-based (Linux/Mac)
            cmd = f'lsof -ti:{port}'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.stdout:
                for pid in result.stdout.strip().split('\n'):
                    if pid:
                        print(f"Killing process {pid} on port {port}...")
                        os.system(f'kill -9 {pid}')
                time.sleep(1)
    except Exception as e:
        print(f"Warning: Error while trying to kill process on port {port}: {e}", file=sys.stderr)

def main():
    settings = Settings()
    
    if settings.use_react_frontend:
        print("React frontend enabled. Starting build process...")
        react_dir = root_dir / "src" / "arbitrator" / "presentation" / "react-ui"
        
        print("Running pnpm install...")
        install_result = subprocess.run(["pnpm", "install"], cwd=str(react_dir), shell=True)
        if install_result.returncode != 0:
            print("Failed to install React dependencies. Exiting.", file=sys.stderr)
            sys.exit(install_result.returncode)
            
        print("Running pnpm build...")
        build_result = subprocess.run(["pnpm", "build"], cwd=str(react_dir), shell=True)
        if build_result.returncode != 0:
            print("Failed to build React frontend. Exiting.", file=sys.stderr)
            sys.exit(build_result.returncode)
            
        print("React frontend build complete.")
    else:
        print("Legacy vanilla JS frontend enabled. Skipping build process.")
        
    print("Starting FastAPI server...")
    # Change working directory to root so uvicorn can find 'main:app'
    os.chdir(str(root_dir))

    # Ensure port is free before starting
    kill_process_on_port(settings.fastapi_port)

    uvicorn.run("main:app", host=settings.fastapi_host, port=settings.fastapi_port, reload=settings.fastapi_reload)

if __name__ == "__main__":
    main()
