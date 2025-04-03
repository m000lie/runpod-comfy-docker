variable "DOCKERHUB_REPO" {
  default = "studiollm"
}

variable "DOCKERHUB_IMG" {
  default = "runpod-worker-comfy"
}

variable "RELEASE_VERSION" {
  default = "latest"
}


group "default" {
  targets = ["base", "rp"]
}

target "base" {
  context = "."
  dockerfile = "Dockerfile"
  target = "base"
  platforms = ["linux/amd64"]
  tags = ["${DOCKERHUB_REPO}/${DOCKERHUB_IMG}:${RELEASE_VERSION}-base"]
}

target "rp" {
  target = "final"
  tags = ["${DOCKERHUB_REPO}/${DOCKERHUB_IMG}:${RELEASE_VERSION}-rp"]
  inherits = ["base"]
}

