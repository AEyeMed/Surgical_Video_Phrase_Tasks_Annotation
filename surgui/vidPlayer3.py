"""Legacy launcher kept for users of earlier SurgUI builds."""

try:
    from .vidPlayer_working import AnnotationTimeline, AnnotationWindow, main
except ImportError:
    from vidPlayer_working import AnnotationTimeline, AnnotationWindow, main  # type: ignore


Window = AnnotationWindow
Slider = AnnotationTimeline


if __name__ == "__main__":
    raise SystemExit(main())
