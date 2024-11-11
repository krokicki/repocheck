import os
import time
import subprocess
import docker
from docker.errors import DockerException

WORK_DIR = os.getcwd() + "/.work"
WORKSPACE_DIR = WORK_DIR + "/workspace"

# Clear the work directory if it exists
if os.path.exists(WORK_DIR):
    try:
        subprocess.run(['rm', '-rf', WORK_DIR], check=True)
        print(f"Deleted work directory: {WORK_DIR}")
    except subprocess.CalledProcessError as e:
        print(f"Error deleting work directory: {e}")

# Create workspace directory
os.makedirs(WORKSPACE_DIR)

# Parameters
GITHUB_REPO_URL = "https://github.com/JaneliaSciComp/zarrcade"  # Replace with the target GitHub repo URL
CONDA_ENV_NAME = "zarrcade"  # Replace with the name of the conda environment from the README
DOCKER_WORKSPACE_DIR = "/workspace"

# Initialize Docker client
print("Connecting to Docker")
try:
    client = docker.from_env()
except DockerException as e:
    print(f"Error connecting to Docker: {e}")
    exit(1)

def build_docker_image():
    print(f"Building Docker image...")
    dockerfile_path = WORK_DIR + "/Dockerfile"
    try:
        # Create a Dockerfile for a conda-based environment
        dockerfile = f"""
        FROM condaforge/miniforge3
        RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
        RUN conda config --prepend envs_dirs {DOCKER_WORKSPACE_DIR}/conda/envs \
            && conda config --prepend pkgs_dirs {DOCKER_WORKSPACE_DIR}/conda/pkgs
        WORKDIR {DOCKER_WORKSPACE_DIR}
        """
        with open(dockerfile_path, "w") as file:
            file.write(dockerfile)
        
        # Build Docker image
        # print("Checking for existing Docker image...")
        # try:
        #     image = client.images.get("sandbox_env:latest")
        #     print("Found existing Docker image")
        # except docker.errors.ImageNotFound:
        #     print("Building new Docker image...")
        image, _ = client.images.build(path=WORK_DIR, tag="sandbox_env:latest", rm=True)

        print("Docker image built successfully.")
        return image
    
    except DockerException as e:
        print(f"Error building Docker image: {e}")
        return None
    finally:
        os.remove(dockerfile_path)



def start_container(image):
    print("Starting container...")
    try:
        # Run the container in detached mode with a bash shell
        container = client.containers.run(
            image,
            "/bin/bash",
            detach=True,
            tty=True,
            volumes={WORKSPACE_DIR: {"bind": "/workspace", "mode": "rw"}},
        )
        print("Container started.")
        return container
    except docker.errors.DockerException as e:
        print(f"Error starting container: {e}")
        return None


def start_persistent_shell(container):
    """Starts a persistent bash shell in the container and returns the exec ID."""
    print("Starting a persistent shell session...")
    exec_id = container.client.api.exec_create(container.id, "/bin/bash", stdin=True, tty=True)
    return exec_id

def run_command_in_shell(container, exec_id, command):
    """Run a command in the persistent shell and retain state between commands."""
    print(f"Running command in shell: {command}")
    sock = container.client.api.exec_start(exec_id, detach=False, tty=True, stream=True, socket=True)
    
    try:
        # Send the command to the shell session
        sock._sock.sendall(f"{command}\n".encode("utf-8"))
        
        # Capture and print output in real-time
        output = ""
        with sock.makefile() as f:
            for line in f:
                decoded_line = line.decode("utf-8")
                output += decoded_line
                print(decoded_line, end="")  # Print each line as it's received

        return output
    finally:
        sock.close()

def setup_project(container, exec_id):
    # Clone the GitHub repository
    print("Cloning GitHub repository...")
    run_command_in_shell(container, exec_id, f"ls -l")
    run_command_in_shell(container, exec_id, f"git clone {GITHUB_REPO_URL} project")

    # Navigate to the project directory
    print("Navigating to project directory...")
    run_command_in_shell(container, exec_id, f"cd project")
    run_command_in_shell(container, exec_id, f"pwd")

    # Set up the conda environment
    print("Setting up conda environment...")
    run_command_in_shell(container, exec_id, f"conda env create -f environment.yml -n {CONDA_ENV_NAME}")

    # Activate the environment and install additional dependencies if specified
    setup_commands = [
        f"conda run -n {CONDA_ENV_NAME} pip install -e .",  # Install in editable mode if needed
    ]

    for command in setup_commands:
        run_command_in_shell(container, exec_id, command)

    print("Project setup completed.")

def main():
    # Build the Docker image
    image = build_docker_image()
    if not image:
        print("Failed to build Docker image.")
        return

    # Start the container
    container = start_container(image)
    if not container:
        print("Failed to start container.")
        return

    try:
        # Start a persistent shell session
        exec_id = start_persistent_shell(container)
        
        # Set up the project
        setup_project(container, exec_id)
    finally:
        # Clean up by stopping and removing the container
        print("Cleaning up container...")
        container.stop()
        container.remove()


if __name__ == "__main__":
    main()


