(function () {
  function scrollPage(direction) {
    var height = window.innerHeight || document.documentElement.clientHeight || 520;
    var amount = Math.max(360, Math.floor(height * 0.86));
    window.scrollBy(0, direction * amount);
  }

  function addControls() {
    var controls = document.createElement("div");
    var up = document.createElement("button");
    var down = document.createElement("button");

    controls.className = "page-controls";
    up.type = "button";
    down.type = "button";
    up.setAttribute("aria-label", "Cuộn lên một trang");
    down.setAttribute("aria-label", "Cuộn xuống một trang");
    up.appendChild(document.createTextNode("▲"));
    down.appendChild(document.createTextNode("▼"));

    up.onclick = function () {
      scrollPage(-1);
      return false;
    };
    down.onclick = function () {
      scrollPage(1);
      return false;
    };

    controls.appendChild(up);
    controls.appendChild(down);
    document.body.appendChild(controls);
  }

  if (document.readyState !== "loading") {
    addControls();
  } else if (document.addEventListener) {
    document.addEventListener("DOMContentLoaded", addControls);
  } else {
    window.onload = addControls;
  }
})();
