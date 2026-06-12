# typed: false
# frozen_string_literal: true

# Homebrew formula for anzuelo - lightweight AI coding metrics
# To install: brew tap bberastegui/tap && brew install anzuelo

class Anzuelo < Formula
  desc "Harness-agnostic lightweight metrics and monitoring for AI coding assistants"
  homepage "https://github.com/bberastegui/anzuelo"
  license "MIT"

  depends_on "python@3"

  resource "anzuelo-pkg" do
    url "https://github.com/bberastegui/anzuelo/archive/v0.1.0.tar.gz"
    sha256 "PLACEHOLDER_SHA256"
  end

  def install
    resource("anzuelo-pkg").stage do
      system "python3", "-m", "pip", "install", "--prefix=#{prefix}", "--no-deps", "."
      bin.install_symlink Dir[libexec/"bin/anzuelo"].first
    end
  end

  test do
    assert_match "anzuelo", shell_output("#{bin}/anzuelo status")
  end
end
