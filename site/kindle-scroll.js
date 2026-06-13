(function () {
  var lastY = null;
  var lastX = null;
  var active = false;
  var multiplier = 1.0;
  var lastMoveEvent = null;

  function getScrollTop() {
    return (
      window.pageYOffset ||
      document.documentElement.scrollTop ||
      document.body.scrollTop ||
      0
    );
  }

  function setScrollTop(value) {
    if (value < 0) {
      value = 0;
    }
    document.documentElement.scrollTop = value;
    document.body.scrollTop = value;
    if (window.scrollTo) {
      window.scrollTo(0, value);
    }
  }

  function firstTouch(event) {
    if (event.touches && event.touches.length) {
      return event.touches[0];
    }
    if (event.changedTouches && event.changedTouches.length) {
      return event.changedTouches[0];
    }
    return null;
  }

  function onTouchStart(event) {
    var touch = firstTouch(event);
    if (!touch) {
      return;
    }
    lastX = touch.clientX;
    lastY = touch.clientY;
    active = true;
  }

  function onTouchMove(event) {
    var touch = firstTouch(event);
    var deltaY;
    var deltaX;
    if (event === lastMoveEvent) {
      return;
    }
    lastMoveEvent = event;

    if (!active || !touch || lastY === null || lastX === null) {
      return;
    }

    deltaY = lastY - touch.clientY;
    deltaX = Math.abs(lastX - touch.clientX);
    lastX = touch.clientX;
    lastY = touch.clientY;

    if (Math.abs(deltaY) < 2 || deltaX > Math.abs(deltaY) * 1.4) {
      return;
    }

    setScrollTop(getScrollTop() + deltaY * multiplier);
  }

  function onTouchEnd() {
    active = false;
    lastX = null;
    lastY = null;
  }

  function attach() {
    document.ontouchstart = onTouchStart;
    document.ontouchmove = onTouchMove;
    document.ontouchend = onTouchEnd;
    document.ontouchcancel = onTouchEnd;
    window.ontouchstart = onTouchStart;
    window.ontouchmove = onTouchMove;
    window.ontouchend = onTouchEnd;
    window.ontouchcancel = onTouchEnd;
    if (document.body) {
      document.body.ontouchstart = onTouchStart;
      document.body.ontouchmove = onTouchMove;
      document.body.ontouchend = onTouchEnd;
      document.body.ontouchcancel = onTouchEnd;
    }
  }

  if (document.readyState !== "loading") {
    attach();
  } else if (document.addEventListener) {
    document.addEventListener("DOMContentLoaded", attach);
  } else {
    window.onload = attach;
  }
})();
