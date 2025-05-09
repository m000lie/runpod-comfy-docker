variable "DOCKERHUB_REPO" {
  default = "studiollm"
}

variable "DOCKERHUB_IMG" {
  default = "runpod-worker-comfy"
}

group "default" {
  targets = ["main"]
}

target "main" {
  context = "."
  dockerfile = "Dockerfile"
  platforms = ["linux/amd64"]
  tags = ["${DOCKERHUB_REPO}/${DOCKERHUB_IMG}:latest"]
}