/* Yanju Foundation — mobile menu, scroll animations, AI chat */
(function () {
  "use strict";

  var PAGES = [
    ["index.html", "Home"],
    ["about.html", "About Us"],
    ["programs.html", "Our Programs"],
    ["gallery.html", "Gallery"],
    ["success-stories.html", "Success Stories"],
    ["volunteer.html", "Volunteer"],
    ["donate.html", "Donate"],
    ["sponsor.html", "Sponsor a Child"],
    ["faq.html", "FAQ & Support"],
  ];
  var current = location.pathname.split("/").pop() || "index.html";

  /* ---------- Mobile menu ---------- */
  function buildMenu() {
    var menu = document.createElement("div");
    menu.className = "yj-menu";
    var links = PAGES.map(function (p) {
      var cls = p[0] === current ? ' class="yj-current"' : "";
      return '<a href="' + p[0] + '"' + cls + ">" + p[1] + "</a>";
    }).join("");
    menu.innerHTML =
      '<button class="yj-menu-close" aria-label="Close menu">&times;</button>' +
      "<nav>" + links + "</nav>" +
      '<div class="yj-menu-cta">' +
      '<a class="yj-cta-donate" href="donate.html">Donate</a>' +
      '<a class="yj-cta-sponsor" href="sponsor.html">Sponsor a Child</a>' +
      "</div>";
    document.body.appendChild(menu);

    function openMenu() {
      menu.classList.add("yj-open");
    }
    menu.querySelector(".yj-menu-close").addEventListener("click", function () {
      menu.classList.remove("yj-open");
    });

    // some pages ship a decorative mobile menu button — wire it instead of
    // injecting a second one
    var existing = Array.prototype.find.call(
      document.querySelectorAll("header button, nav button"),
      function (b) {
        return b.textContent.trim() === "menu" && b.querySelector(".material-symbols-outlined");
      }
    );
    if (existing) {
      existing.addEventListener("click", openMenu);
      return;
    }

    var burger = document.createElement("button");
    burger.className = "yj-burger";
    burger.setAttribute("aria-label", "Open menu");
    burger.innerHTML = "<span></span><span></span><span></span>";
    burger.addEventListener("click", openMenu);

    // put the burger next to the header's CTA buttons (Donate row)
    var cta = document.querySelector(
      'header a[href="donate.html"], nav a[href="donate.html"]'
    );
    var host =
      (cta && cta.parentElement) ||
      document.querySelector("header .flex.justify-between") ||
      document.querySelector("nav .flex.justify-between") ||
      document.querySelector("header > div.flex") ||
      document.querySelector("nav > div.flex");
    if (host) {
      host.appendChild(burger);
    } else {
      burger.style.position = "fixed";
      burger.style.top = "16px";
      burger.style.right = "16px";
      burger.style.zIndex = "60";
      document.body.appendChild(burger);
    }
  }

  /* ---------- Scroll reveal ---------- */
  function buildReveal() {
    if (!("IntersectionObserver" in window)) return;
    var targets = document.querySelectorAll(
      "main section:not(.no-reveal), section:not(.no-reveal), footer:not(.no-reveal)"
    );
    var seen = new Set();
    var list = [];
    targets.forEach(function (el) {
      if (!seen.has(el)) {
        seen.add(el);
        list.push(el);
      }
    });
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) {
            e.target.classList.add("yj-visible");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.08 }
    );
    list.forEach(function (el) {
      el.classList.add("yj-reveal");
      io.observe(el);
    });
  }

  /* ---------- Chat ---------- */
  var GREETING =
    "Hello! I'm the Yanju Foundation assistant. Ask me about our programs, scholarships, donations, or volunteering.";
  var history = []; // {role, content}

  function askAPI(text, onReply) {
    history.push({ role: "user", content: text });
    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history.slice(-12) }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var reply = d.reply || "Sorry, something went wrong. Please try again.";
        history.push({ role: "assistant", content: reply });
        onReply(reply);
      })
      .catch(function () {
        onReply(
          "I couldn't reach the assistant right now. Please email us at yanjufoundation@gmail.com or call +234 704 744 4628."
        );
      });
  }

  function buildFloatingChat() {
    var root = document.createElement("div");
    root.id = "yj-chat-root";
    root.innerHTML =
      '<div id="yj-chat-window">' +
      '<div class="yj-chat-head"><div><div class="yj-title">Yanju Assistant</div>' +
      '<div class="yj-sub">Online — we’re here to help!</div></div>' +
      '<button id="yj-chat-close" aria-label="Close chat">&times;</button></div>' +
      '<div id="yj-chat-thread"></div>' +
      '<div class="yj-chat-inputrow">' +
      '<input id="yj-chat-input" type="text" placeholder="Ask a question..." />' +
      '<button id="yj-chat-send" aria-label="Send">&#10148;</button></div>' +
      "</div>" +
      '<button id="yj-chat-toggle" aria-label="Chat with us">' +
      '<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2z"/></svg>' +
      "</button>";
    document.body.appendChild(root);

    var win = root.querySelector("#yj-chat-window");
    var thread = root.querySelector("#yj-chat-thread");
    var input = root.querySelector("#yj-chat-input");

    function addMsg(text, who) {
      var b = document.createElement("div");
      b.className = "yj-msg yj-msg-" + who;
      b.textContent = text;
      thread.appendChild(b);
      thread.scrollTop = thread.scrollHeight;
      return b;
    }

    addMsg(GREETING, "bot");

    function send() {
      var text = input.value.trim();
      if (!text) return;
      input.value = "";
      addMsg(text, "user");
      var typing = addMsg("Typing…", "bot");
      typing.classList.add("yj-msg-typing");
      askAPI(text, function (reply) {
        typing.classList.remove("yj-msg-typing");
        typing.textContent = reply;
        thread.scrollTop = thread.scrollHeight;
      });
    }

    root.querySelector("#yj-chat-toggle").addEventListener("click", function () {
      win.classList.toggle("yj-open");
      if (win.classList.contains("yj-open")) input.focus();
    });
    root.querySelector("#yj-chat-close").addEventListener("click", function () {
      win.classList.remove("yj-open");
    });
    root.querySelector("#yj-chat-send").addEventListener("click", send);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") send();
    });
  }

  function wireEmbeddedChat(input) {
    // FAQ page: reuse the designed chat panel
    var thread = document.querySelector("div.flex-1.overflow-y-auto");
    var sendBtn = input.parentElement.querySelector("button");
    if (!thread) return;

    function botBubble(text, typing) {
      var wrap = document.createElement("div");
      wrap.className = "chat-bubble-in flex items-end gap-3 max-w-[85%]";
      wrap.innerHTML =
        '<div class="w-8 h-8 rounded-full bg-primary-container flex-shrink-0 flex items-center justify-center text-white">' +
        '<span class="material-symbols-outlined text-sm" style="font-variation-settings: \'FILL\' 1;">smart_toy</span></div>' +
        '<div class="bg-surface-container-high p-4 rounded-2xl rounded-bl-none shadow-sm text-on-surface-variant font-body-md" style="white-space:pre-wrap"></div>';
      var body = wrap.lastElementChild;
      body.textContent = text;
      if (typing) body.style.fontStyle = "italic";
      thread.appendChild(wrap);
      thread.scrollTop = thread.scrollHeight;
      return body;
    }
    function userBubble(text) {
      var wrap = document.createElement("div");
      wrap.className = "chat-bubble-in flex flex-row-reverse items-end gap-3 max-w-[85%] ml-auto";
      wrap.innerHTML =
        '<div class="bg-primary p-4 rounded-2xl rounded-br-none shadow-sm text-white font-body-md" style="white-space:pre-wrap"></div>';
      wrap.firstElementChild.textContent = text;
      thread.appendChild(wrap);
      thread.scrollTop = thread.scrollHeight;
    }

    function send(textOverride) {
      var text = (textOverride || input.value).trim();
      if (!text) return;
      input.value = "";
      userBubble(text);
      var body = botBubble("Typing…", true);
      askAPI(text, function (reply) {
        body.style.fontStyle = "";
        body.textContent = reply;
        thread.scrollTop = thread.scrollHeight;
      });
    }

    if (sendBtn) sendBtn.addEventListener("click", function () { send(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") send();
    });
  }

  /* ---------- Footer cleanup: contact info lives only in the strip ---------- */
  function dedupeFooter() {
    document.querySelectorAll("footer").forEach(function (footer) {
      // email / phone rows duplicated from the contact strip
      footer.querySelectorAll('a[href^="mailto:"], a[href^="tel:"]').forEach(function (a) {
        if (a.closest(".yj-footer-contact")) return;
        var row = a.closest("li") || (a.parentElement.tagName === "P" ? a.parentElement : a);
        row.remove();
      });
      // icon-only social buttons (the strip already links Instagram/email)
      footer.querySelectorAll("a").forEach(function (a) {
        if (a.closest(".yj-footer-contact")) return;
        var t = a.textContent.trim();
        if (a.querySelector(".material-symbols-outlined") && /^[a-z_]+$/.test(t)) a.remove();
      });
      // address / raw phone lines and now-empty social rows
      footer.querySelectorAll("li, p").forEach(function (el) {
        if (el.closest(".yj-footer-contact")) return;
        var t = el.textContent.replace(/\s+/g, " ").trim();
        if (/^(location_on\s*)?Lagos, Nigeria$/.test(t) || /\+234[\d ()-]+$/.test(t)) el.remove();
      });
      // drop columns/headings left with no content (e.g. "Contact Info", "Follow Our Journey")
      footer.querySelectorAll("h4, h5").forEach(function (h) {
        var col = h.parentElement;
        var hasContent = col.querySelector("a, input") || col.textContent.replace(h.textContent, "").trim().length > 5;
        if (!hasContent) col.remove();
      });
    });
  }

  /* ---------- Animated stat counters (e.g. 2,500+ children supported) ---------- */
  function buildCounters() {
    if (!("IntersectionObserver" in window)) return;
    var els = [];
    document.querySelectorAll("main *, section *").forEach(function (el) {
      if (el.children.length) return;
      var t = el.textContent.trim();
      if (!/^\d{1,3}(,\d{3})*\+?$/.test(t)) return;
      if (parseInt(t.replace(/,/g, ""), 10) < 10) return;
      if (parseFloat(getComputedStyle(el).fontSize) < 22) return;
      els.push(el);
    });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        var el = e.target;
        var raw = el.textContent.trim();
        var plus = raw.indexOf("+") > -1;
        var target = parseInt(raw.replace(/[,+]/g, ""), 10);
        var start = null;
        function tick(ts) {
          if (!start) start = ts;
          var p = Math.min((ts - start) / 1400, 1);
          var eased = 1 - Math.pow(1 - p, 3);
          var val = Math.round(target * eased);
          el.textContent = val.toLocaleString("en-NG") + (plus && p === 1 ? "+" : "");
          if (p < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      });
    }, { threshold: 0.4 });
    els.forEach(function (el) { io.observe(el); });
  }

  function wireNewsletterForm() {
    var form = document.getElementById("newsletter-form");
    if (!form) return;
    var msg = document.getElementById("newsletter-form-message");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var btn = form.querySelector("button");
      var originalText = btn.textContent;
      btn.disabled = true;
      msg.classList.add("hidden");
      fetch("/api/newsletter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: form.email.value }),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { ok: res.ok, data: data };
          });
        })
        .then(function (result) {
          if (!result.ok) throw new Error(result.data.error || "Something went wrong.");
          msg.textContent = "Thanks for subscribing!";
          msg.classList.remove("hidden");
          form.reset();
          btn.disabled = false;
        })
        .catch(function (err) {
          msg.textContent = err.message || "Could not subscribe. Please try again.";
          msg.classList.remove("hidden");
          btn.disabled = false;
        })
        .finally(function () {
          btn.textContent = originalText;
        });
    });
  }

  function wireSuccessCarousel() {
    var root = document.getElementById("success-carousel");
    if (!root) return;
    var slides = Array.prototype.slice.call(root.querySelectorAll(".carousel-slide"));
    var dots = Array.prototype.slice.call(root.querySelectorAll("#carousel-dots button"));
    var prevBtn = document.getElementById("carousel-prev");
    var nextBtn = document.getElementById("carousel-next");
    var current = 0;
    var timer;

    function show(index) {
      current = (index + slides.length) % slides.length;
      slides.forEach(function (slide, i) {
        slide.classList.toggle("hidden", i !== current);
      });
      dots.forEach(function (dot, i) {
        dot.classList.toggle("bg-primary", i === current);
        dot.classList.toggle("bg-outline-variant", i !== current);
      });
    }

    function restartAutoplay() {
      clearInterval(timer);
      timer = setInterval(function () { show(current + 1); }, 7000);
    }

    prevBtn.addEventListener("click", function () { show(current - 1); restartAutoplay(); });
    nextBtn.addEventListener("click", function () { show(current + 1); restartAutoplay(); });
    dots.forEach(function (dot, i) {
      dot.addEventListener("click", function () { show(i); restartAutoplay(); });
    });

    show(0);
    restartAutoplay();
  }

  function wireNewsletterWidgets() {
    document.querySelectorAll(".yj-newsletter-widget").forEach(function (widget) {
      var input = widget.querySelector(".yj-newsletter-input");
      var btn = widget.querySelector(".yj-newsletter-submit");
      var msg = widget.parentElement.querySelector(".yj-newsletter-message");
      if (!input || !btn) return;

      function submit() {
        var email = input.value.trim();
        if (!email) return;
        btn.disabled = true;
        fetch("/api/newsletter", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email }),
        })
          .then(function (res) {
            return res.json().then(function (data) {
              return { ok: res.ok, data: data };
            });
          })
          .then(function (result) {
            if (!result.ok) throw new Error(result.data.error || "Something went wrong.");
            if (msg) {
              msg.textContent = "Thanks for subscribing!";
              msg.classList.remove("hidden");
            }
            input.value = "";
          })
          .catch(function (err) {
            if (msg) {
              msg.textContent = err.message || "Could not subscribe. Please try again.";
              msg.classList.remove("hidden");
            }
          })
          .finally(function () {
            btn.disabled = false;
          });
      }

      btn.addEventListener("click", function (e) {
        e.preventDefault();
        submit();
      });
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          submit();
        }
      });
    });
  }

  function init() {
    buildMenu();
    buildReveal();
    dedupeFooter();
    buildCounters();
    wireNewsletterForm();
    wireNewsletterWidgets();
    wireSuccessCarousel();
    var embedded = document.querySelector('input[placeholder="Type your message..."]');
    if (embedded) {
      wireEmbeddedChat(embedded);
    } else {
      buildFloatingChat();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
