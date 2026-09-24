var core = {
  "start": function () {
    core.load();
  },
  "install": function () {
    core.load();
  },
  "load": function () {
    core.update.toolbar.button();
  },
  "clean": {
    "session": {
      "tabs": async function (tabId) {
        if (tabId) {
          const target = config.session.map.tabs[tabId];
          if (target) {
            if (target.length) {
              const removeRuleIds = target.map(e => e.id);
              /*  */
              await app.netrequest.rules.remove.by.ids(removeRuleIds);
              delete config.session.map.tabs[tabId];
            }
          }
        } else {
          for (let tabId in config.session.map.tabs) {
            const target = config.session.map.tabs[tabId];
            if (target) {
              if (target.length) {
                const removeRuleIds = target.map(e => e.id);
                /*  */
                await app.netrequest.rules.remove.by.ids(removeRuleIds);
                delete config.session.map.tabs[tabId];
              }
            }
          }
        }
      }
    }
  },
  "update": {
    "toolbar": {
      "button": function () {
        app.button.title(null, "Access-Control-Allow-Origin: " + config.addon.state);
        app.button.icon(null, config.addon.state === "ON" && config.addon.includelist.length ? "CUST" : config.addon.state);
      }
    },
    "state": function () {
      config.addon.state = config.addon.state === "ON" ? "OFF" : "ON";
      /*  */
      core.update.popup();
      core.update.toolbar.button();
    },
    "popup": function () {
      app.tab.query.active(function (tab) {
        app.popup.send("storage", {
          "tab": tab,
          "excludelist": config.addon.excludelist,
          "includelist": config.addon.includelist,
          "_state": config.addon.state === "ON" && config.addon.includelist.length ? "CUST" : config.addon.state
        });
      });
    },
    "options": function () {
      app.options.send("storage", {
        "patch": config.cors.patch,
        "origin": config.cors.origin,
        "rules": config.custom.rules,
        "methods": config.cors.methods,
        "headers": config.cors.headers,
        "sub_frame": config.cors.sub_frame,
        "main_frame": config.cors.main_frame,
        "domain_type": config.cors.domain_type,
        "excludelist": config.addon.excludelist,
        "includelist": config.addon.includelist,
        "credentials": config.cors.credentials
      });
    },
    "addon": async function (data) {
      if ("state" in data) {
        core.update.toolbar.button();
      }
      /*  */
      if ("tabs" in data === false) {
        await core.register.all.requests();
      }
      /*  */
      if ("sub_frame" in data || "main_frame" in data) {
        await core.clean.session.tabs();
      }
      /*  */
      if ("whitelist" in data || "includelist" in data) {
        core.update.options();
        core.update.toolbar.button();
      }
    },
    "custom": {
      "rules": {
        "add": function (e) {
          let tmp = config.custom.rules;
          tmp[e.id] = e;
          config.custom.rules = tmp;
          /*  */
          core.update.options();
        },
        "remove": function (e) {
          app.netrequest.rules.remove.by.ids([Number(e.id)]);
          /*  */
          let tmp = config.custom.rules;
          delete tmp[e.id];
          config.custom.rules = tmp;
          /*  */
          core.update.options();
        }
      }
    },
    "excludelist": function () {
      app.tab.query.active(function (tab) {
        if (tab && tab.url) {
          if (tab.url.indexOf("http") === 0) {
            let includelist = config.addon.includelist;
            let excludelist = config.addon.excludelist;
            let hostname = (new URL(tab.url)).hostname;
            /*  */
            const index = excludelist.indexOf(hostname);
            if (index !== -1) {
              excludelist.splice(index, 1);
            } else {
              excludelist.push(hostname);
              includelist = includelist.filter(e => e !== hostname);
              excludelist = excludelist.filter(function (a, b) {
                return excludelist.indexOf(a) === b;
              });
            }
            /*  */
            config.addon.includelist = includelist;
            config.addon.excludelist = excludelist;
          }
        }
        /*  */
        core.update.popup();
      });
    },
    "includelist": function () {
      app.tab.query.active(function (tab) {
        if (tab && tab.url) {
          if (tab.url.indexOf("http") === 0) {
            let includelist = config.addon.includelist;
            let excludelist = config.addon.excludelist;
            let hostname = (new URL(tab.url)).hostname;
            /*  */
            const index = includelist.indexOf(hostname);
            if (index !== -1) {
              includelist.splice(index, 1);
            } else {
              includelist.push(hostname);
              excludelist = excludelist.filter(e => e !== hostname);
              includelist = includelist.filter(function (a, b) {
                return includelist.indexOf(a) === b;
              });
            }
            /*  */
            config.addon.includelist = includelist;
            config.addon.excludelist = excludelist;
          }
        }
        /*  */
        core.update.popup();
      });
    }
  },
  "register": {
    "action": false,
    "init": function () {
      core.register.webrequest.callback();
      core.register.all.requests();
    },
    "all": {
      "requests": async function () {
        if (core.register.action) return;
        /*  */
        core.register.action = true;
        await core.register.webrequest.global();
        await core.register.netrequest.global();
        /*  */
        await core.register.netrequest.custom();
        await core.register.netrequest.tabs();
        core.register.action = false;
      }
    },
    "webrequest": {
      "global": async function () {
        app.webrequest.on.before.request.remove();
        /*  */
        if (config.addon.state === "ON") {
          if (config.cors.origin === false) {
            const types = [];
            if (config.cors.sub_frame) types.push("sub_frame");
            if (config.cors.main_frame) types.push("main_frame");
            /*  */
            if (types.length) {
              app.webrequest.on.before.request.add({
                "types": types,
                "urls": ["*://*/*"]
              });
            }
          }
        }
      },
      "callback": function () {
        app.webrequest.on.before.request.callback(function (info) {
          if (info.type === "main_frame") {
            core.clean.session.tabs(info.tabId);
          }
          /*  */
          const id = Number(info.requestId);
          const tmp = config.session.map.tabs;
          const origin = (new URL(info.url)).origin;
          const hostname = (new URL(info.url)).hostname;
          /*  */
          const target = tmp[info.tabId] || [];
          target.push({
            "id": id,
            "origin": origin,
            "hostname": hostname
          });
          /*  */
          tmp[info.tabId] = target;
          config.session.map.tabs = tmp;
          core.register.netrequest.tab(target);
        });
      }
    },
    "netrequest": {
      "tabs": async function () {
        app.tab.query.all({}, async function (tabs) {
          if (tabs && tabs.length) {
            for (let i = 0; i < tabs.length; i++) {
              const tab = tabs[i];
              if (tab) {
                const target = config.session.map.tabs[tab.id];
                if (target) {
                  await core.register.netrequest.tab(target);
                }
              }
            }
          }
        });
      },
      "tab": async function (e) {
        if (config.addon.state === "ON") {
          if (config.cors.origin === false) {
            if (e) {
              if (e.length) {
                for (let i = 0; i < e.length; i++) {
                  const cond_3 = config.addon.includelist.length === 0;
                  const cond_4 = config.addon.includelist.includes(e[i].hostname);
                  /*  */
                  if (cond_3 || cond_4) {
                    app.netrequest.rules.push({
                      "priority": 2,
                      "id": e[i].id,
                      "condition": {
                        "urlFilter": '*',
                        "initiatorDomains": [e[i].hostname],
                        ...(config.cors.domain_type !== "all") && ({"domainType": config.cors.domain_type}),
                        ...(config.addon.excludelist.length) && ({"excludedInitiatorDomains": config.addon.excludelist})
                      },
                      "action": {
                        "type": "modifyHeaders",
                        "responseHeaders": [{
                          "operation": "set", 
                          "value": e[i].origin,
                          "header": "Access-Control-Allow-Origin"
                        }]
                      }
                    });
                  }
                }
                /*  */
                await app.netrequest.rules.update();
              }
            }
          }
        }
      },
      "custom": async function () {
        if (config.addon.state === "ON") {
          for (let id in config.custom.rules) {
            const rule = config.custom.rules[id];
            if (rule) {
              if (rule.state === true) {
                const methods = {};
                methods.a = config.cors.methods.split(',').map(e => e.trim()).filter(e => e);
                methods.b = rule.methods.split(',').map(e => e.trim()).filter(e => e);
                methods.c = [...new Set([...methods.a, ...methods.b])].join(", ");
                /*  */
                app.netrequest.rules.push({
                  "priority": 3,
                  "id": rule.id,
                  "condition": {
                    "urlFilter": '*',
                    ...(rule.type !== "all") && ({"domainType": rule.type}),
                    ...(rule.domain === "requestDomains") && ({"requestDomains": [rule.hostname]}),
                    ...(rule.domain === "initiatorDomains") && ({"initiatorDomains": [rule.hostname]})
                  },
                  "action": {
                    "type": "modifyHeaders",
                    "responseHeaders": [
                      ...(rule.origin) && [{"operation": "set", "value": rule.origin, "header": "Access-Control-Allow-Origin"}],
                      ...(rule.methods) && [{"operation": "append", "value": methods.c, "header": "Access-Control-Allow-Methods"}],
                      ...(rule.headers) && [{"operation": "append", "value": rule.headers, "header": "Access-Control-Allow-Headers"}],
                      ...(rule.credentials) && [{"operation": "set", "value": rule.credentials, "header": "Access-Control-Allow-Credentials"}]
                    ]
                  }
                });
              }
            }
          }
          /*  */
          await app.netrequest.rules.update();
        }
      },
      "global": async function () {
        app.netrequest.rules.scope = "session";
        /*  */
        await app.netrequest.display.badge.text(false);
        await app.netrequest.rules.remove.by.action.type("modifyHeaders", "responseHeaders");
        /*  */
        if (config.addon.state === "ON") {
          const rules = {
            'a': {
              "value": '*',
              "operation": "set",
              "header": "Access-Control-Allow-Origin"
            },
            'b': {
              "operation": "set",
              "value": config.cors.methods,
              "header": "Access-Control-Allow-Methods"
            },
            'c': {
              "value": '*',
              "operation": "set",
              "header": "Access-Control-Allow-Headers"
            },
            'd': {
              "value": "true",
              "operation": "set",
              "header": "Access-Control-Allow-Credentials"
            },
            'e': {
              "value": "PATCH",
              "header": "Allow",
              "operation": "set"
            },
            'f': {
              "operation": "append",
              "value": "Content-Type",
              "header": "Access-Control-Allow-Headers"
            },
            'g': {
              "operation": "append",
              "header": "Access-Control-Allow-Methods",
              "value": config.cors.methods.split(',').map(e => e.trim()).filter(e => e && e !== "PATCH").join(", ") + ", PATCH"
            }
          };
          /*  */
          const responseHeaders = [];
          responseHeaders.push(rules.a);
          responseHeaders.push(rules.b);
          if (config.cors.headers) responseHeaders.push(rules.c);
          if (config.cors.credentials) responseHeaders.push(rules.d);
          /*  */
          app.netrequest.rules.push({
            "priority": 1,
            "action": {
              "type": "modifyHeaders",
              "responseHeaders": responseHeaders
            },
            "condition": {
              "urlFilter": '*',
              ...(config.cors.domain_type !== "all") && ({"domainType": config.cors.domain_type}),
              ...(config.addon.includelist.length) && ({"initiatorDomains": config.addon.includelist}),
              ...(config.addon.excludelist.length) && ({"excludedInitiatorDomains": config.addon.excludelist})
            }
          });
          /*  */
          if (config.cors.patch) {
            app.netrequest.rules.push({
              "priority": 1,
              "action": {
                "type": "modifyHeaders",
                "responseHeaders": [rules.e, rules.f, rules.g]
              },
              "condition": {
                "urlFilter": '*',
                "requestMethods": ["options"],
                ...(config.cors.domain_type !== "all") && ({"domainType": config.cors.domain_type}),
                ...(config.addon.includelist.length) && ({"initiatorDomains": config.addon.includelist}),
                ...(config.addon.excludelist.length) && ({"excludedInitiatorDomains": config.addon.excludelist})
              }
            });
          }
        }
        /*  */
        await app.netrequest.rules.update();
      }
    }
  }
};

app.popup.receive("load", core.update.popup);
app.popup.receive("options", app.tab.options);
app.popup.receive("toggle", core.update.state);
app.popup.receive("excludelist", core.update.excludelist);
app.popup.receive("includelist", core.update.includelist);

app.popup.receive("reload", function () {app.tab.reload(null, true)});
app.popup.receive("support", function () {app.tab.open(app.homepage())});
app.popup.receive("test", function () {app.tab.open(config.addon.page.test)});
app.popup.receive("tutorial", function () {app.tab.open(config.addon.page.tutorial)});
app.popup.receive("donation", function () {app.tab.open(app.homepage() + "?reason=support")});

app.options.receive("load", core.update.options);
app.options.receive("add-custom-rule", core.update.custom.rules.add);
app.options.receive("remove-custom-rule", core.update.custom.rules.remove);

app.options.receive("patch", function (e) {config.cors.patch = e});
app.options.receive("origin", function (e) {config.cors.origin = e});
app.options.receive("methods", function (e) {config.cors.methods = e});
app.options.receive("headers", function (e) {config.cors.headers = e});
app.options.receive("sub_frame", function (e) {config.cors.sub_frame = e});
app.options.receive("main_frame", function (e) {config.cors.main_frame = e});
app.options.receive("excludelist", function (e) {config.addon.excludelist = e});
app.options.receive("includelist", function (e) {config.addon.includelist = e});
app.options.receive("credentials", function (e) {config.cors.credentials = e});
app.options.receive("domain_type", function (e) {config.cors.domain_type = e});

app.storage.load(core.register.init);
app.hotkey.on.pressed(core.update.state);
app.tab.on.removed(core.clean.session.tabs);

app.on.startup(core.start);
app.on.installed(core.install);
app.on.storage(core.update.addon);
