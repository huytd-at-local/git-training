(function () {
  var controls = null;
  var lastTouch = 0;

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

  function getViewHeight() {
    return (
      window.innerHeight ||
      document.documentElement.clientHeight ||
      document.body.clientHeight ||
      520
    );
  }

  function updateControls() {
    var top;
    if (!controls) {
      return;
    }
    top = getScrollTop() + Math.max(80, Math.floor((getViewHeight() - controls.offsetHeight) / 2));
    controls.style.top = top + "px";
  }

  function scrollPage(direction) {
    var amount = Math.max(420, Math.floor(getViewHeight() * 0.82));
    setScrollTop(getScrollTop() + direction * amount);
    updateControls();
  }

  function scrollTop() {
    setScrollTop(0);
    updateControls();
  }

  function bindButton(button, action) {
    button.onclick = function () {
      if (new Date().getTime() - lastTouch < 700) {
        return false;
      }
      action();
      return false;
    };
    button.ontouchstart = function () {
      lastTouch = new Date().getTime();
      action();
      return false;
    };
  }

  function addControls() {
    var top = document.createElement("button");
    var up = document.createElement("button");
    var down = document.createElement("button");

    controls = document.createElement("div");
    controls.className = "page-controls";
    top.type = "button";
    up.type = "button";
    down.type = "button";
    top.className = "top-button";
    top.setAttribute("aria-label", "Trở lại đầu trang");
    up.setAttribute("aria-label", "Cuộn lên một trang");
    down.setAttribute("aria-label", "Cuộn xuống một trang");
    top.appendChild(document.createTextNode("TOP"));
    up.appendChild(document.createTextNode("▲"));
    down.appendChild(document.createTextNode("▼"));

    bindButton(top, scrollTop);
    bindButton(up, function () {
      scrollPage(-1);
    });
    bindButton(down, function () {
      scrollPage(1);
    });

    controls.appendChild(top);
    controls.appendChild(up);
    controls.appendChild(down);
    document.body.appendChild(controls);
    updateControls();
    window.onscroll = updateControls;
    window.onresize = updateControls;
    window.setInterval(updateControls, 800);
  }

  if (document.readyState !== "loading") {
    addControls();
  } else if (document.addEventListener) {
    document.addEventListener("DOMContentLoaded", addControls);
  } else {
    window.onload = addControls;
  }
})();
