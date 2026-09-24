var background = {
  "port": null,
  "message": {},
  "receive": function (id, callback) {
    if (id) {
      background.message[id] = callback;
    }
  },
  "send": function (id, data) {
    if (id) {
      chrome.runtime.sendMessage({
        "method": id,
        "data": data,
        "path": "popup-to-background"
      }, function () {
        return chrome.runtime.lastError;
      });
    }
  },
  "connect": function (port) {
    chrome.runtime.onMessage.addListener(background.listener); 
    /*  */
    if (port) {
      background.port = port;
      background.port.onMessage.addListener(background.listener);
      background.port.onDisconnect.addListener(function () {
        background.port = null;
      });
    }
  },
  "post": function (id, data) {
    if (id) {
      if (background.port) {
        background.port.postMessage({
          "method": id,
          "data": data,
          "path": "popup-to-background",
          "port": background.port.name
        });
      }
    }
  },
  "listener": function (e) {
    if (e) {
      for (let id in background.message) {
        if (background.message[id]) {
          if ((typeof background.message[id]) === "function") {
            if (e.path === "background-to-popup") {
              if (e.method === id) {
                background.message[id](e.data);
              }
            }
          }
        }
      }
    }
  }
};

var config = {
  "removeAttributes": function (e, ...attributes) {
    attributes.forEach(a => e.removeAttribute(a));
  },
  "load": function () {
    const test = document.querySelector(".test");
    const reload = document.querySelector(".reload");
    const support = document.querySelector(".support");
    const options = document.querySelector(".options");
    const explore = document.getElementById("explore");
    const donation = document.querySelector(".donation");
    const tutorial = document.querySelector(".tutorial");
    const toggle = document.querySelector(".toggle .button");
    const excludelist = document.querySelector(".excludelist");
    const includelist = document.querySelector(".includelist");
    /*  */
    test.addEventListener("click", function () {background.send("test")});
    reload.addEventListener("click", function () {background.send("reload")});
    toggle.addEventListener("click", function () {background.send("toggle")});
    support.addEventListener("click", function () {background.send("support")});
    options.addEventListener("click", function () {background.send("options")});
    tutorial.addEventListener("click", function () {background.send("tutorial")});
    donation.addEventListener("click", function () {background.send("donation")});
    excludelist.addEventListener("click", function () {background.send("excludelist")});
    includelist.addEventListener("click", function () {background.send("includelist")});
    /*  */
    background.send("load");
    window.removeEventListener("load", config.load, false);
    if (navigator.userAgent.indexOf("Edg") !== -1) explore.style.display = "none";
  },
  "render": function (e) {
    const toggle = document.querySelector(".toggle .button");
    const excludelist = document.querySelector(".excludelist");
    const includelist = document.querySelector(".includelist");
    /*  */
    config.removeAttributes(toggle, "include", "exclude", "error");
    config.removeAttributes(includelist, "loaded", "added", "error");
    config.removeAttributes(excludelist, "loaded", "added", "error");
    toggle.setAttribute("state", e._state);
    /*  */
    if (e) {
      if (e.tab) {
        if (e.tab.url) {
          if (e.tab.url.indexOf("http") === 0) {
            if (e.excludelist) {
              if (e.excludelist.length) {
                const hostname = (new URL(e.tab.url)).hostname;
                if (e.excludelist.indexOf(hostname) !== -1) {
                  excludelist.setAttribute("added", '');
                  toggle.setAttribute("exclude", '');
                }
              }
            }
            /*  */
            if (e.includelist) {
              if (e.includelist.length) {
                const hostname = (new URL(e.tab.url)).hostname;
                if (e.includelist.indexOf(hostname) !== -1) {
                  includelist.setAttribute("added", '');
                  toggle.setAttribute("include", '');
                }
              }
            }
          } else {
            toggle.setAttribute("error", '');
          }
        } else {
          toggle.setAttribute("error", '');
        }
      } else {
        toggle.setAttribute("error", '');
      }
    }
  }
};

background.receive("storage", config.render);
background.connect(chrome.runtime.connect({"name": "popup"}));

window.addEventListener("load", config.load, false);
