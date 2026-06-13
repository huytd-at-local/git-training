(function () {
  var controls = null;
  var jumps = [];

  function getScrollTop() {
    return (
      window.pageYOffset ||
      document.documentElement.scrollTop ||
      document.body.scrollTop ||
      0
    );
  }

  function getOffsetTop(element) {
    var top = 0;
    while (element) {
      top += element.offsetTop || 0;
      element = element.offsetParent;
    }
    return top;
  }

  function byTag(root, tagName) {
    var list = root.getElementsByTagName(tagName);
    var result = [];
    var i;
    for (i = 0; i < list.length; i += 1) {
      result.push(list[i]);
    }
    return result;
  }

  function sortByPagePosition(a, b) {
    return getOffsetTop(a) - getOffsetTop(b);
  }

  function collectBlocks(main) {
    var blocks = [];
    blocks = blocks.concat(byTag(main, "h2"));
    blocks = blocks.concat(byTag(main, "h3"));
    blocks = blocks.concat(byTag(main, "p"));
    blocks.sort(sortByPagePosition);
    return blocks;
  }

  function addJumpBefore(block, id) {
    var jump = document.createElement("a");
    jump.className = "page-jump";
    jump.id = id;
    jump.name = id;
    if (block.parentNode) {
      block.parentNode.insertBefore(jump, block);
    }
    return jump;
  }

  function buildJumps(main) {
    var blocks = collectBlocks(main);
    var lastTop = -9999;
    var i;
    var top;

    main.id = main.id || "top";
    jumps.push(main);

    for (i = 0; i < blocks.length; i += 1) {
      top = getOffsetTop(blocks[i]);
      if (top - lastTop >= 520) {
        jumps.push(addJumpBefore(blocks[i], "page-jump-" + jumps.length));
        lastTop = top;
      }
    }
  }

  function currentJumpIndex() {
    var position = getScrollTop() + 60;
    var index = 0;
    var i;
    for (i = 0; i < jumps.length; i += 1) {
      if (getOffsetTop(jumps[i]) <= position) {
        index = i;
      } else {
        break;
      }
    }
    return index;
  }

  function setHref(link, jump) {
    link.href = "#" + jump.id;
  }

  function updateControls() {
    var index;
    var topLink;
    var upLink;
    var downLink;
    if (!controls || jumps.length === 0) {
      return;
    }

    index = currentJumpIndex();
    topLink = controls.getElementsByTagName("a")[0];
    upLink = controls.getElementsByTagName("a")[1];
    downLink = controls.getElementsByTagName("a")[2];
    setHref(topLink, jumps[0]);
    setHref(upLink, jumps[Math.max(0, index - 1)]);
    setHref(downLink, jumps[Math.min(jumps.length - 1, index + 1)]);
    controls.style.top = getScrollTop() + 150 + "px";
  }

  function makeLink(className, text, label) {
    var link = document.createElement("a");
    link.className = className;
    link.href = "#top";
    link.setAttribute("aria-label", label);
    link.appendChild(document.createTextNode(text));
    link.onclick = updateControls;
    link.ontouchstart = updateControls;
    return link;
  }

  function addControls() {
    var main = document.getElementsByTagName("main")[0];
    if (!main) {
      return;
    }

    buildJumps(main);
    controls = document.createElement("div");
    controls.className = "page-controls";
    controls.appendChild(makeLink("top-button", "TOP", "Trở lại đầu trang"));
    controls.appendChild(makeLink("", "▲", "Lùi lại một đoạn"));
    controls.appendChild(makeLink("", "▼", "Tới đoạn tiếp theo"));
    document.body.appendChild(controls);

    updateControls();
    window.onscroll = updateControls;
    window.onresize = updateControls;
    window.setInterval(updateControls, 700);
  }

  if (document.readyState !== "loading") {
    addControls();
  } else if (document.addEventListener) {
    document.addEventListener("DOMContentLoaded", addControls);
  } else {
    window.onload = addControls;
  }
})();
