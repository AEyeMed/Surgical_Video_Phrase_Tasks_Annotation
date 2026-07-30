"""Backward-compatible entry point for the unified SurgiAnnotate workbench."""

try:
    from .vidPlayer_working import AnnotationTimeline, AnnotationWindow, main
except ImportError:
    from vidPlayer_working import AnnotationTimeline, AnnotationWindow, main  # type: ignore


Window = AnnotationWindow
VideoPlayerWindow = AnnotationWindow
Slider = AnnotationTimeline


if __name__ == "__main__":
    raise SystemExit(main())
