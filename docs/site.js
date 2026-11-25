/* Small, dependency-free enhancements. Downloads never depend on JavaScript. */
(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const readPreference = () => {
    try {
      return localStorage.getItem("aiclip-motion");
    } catch (_) {
      return null;
    }
  };
  let manuallyReduced = readPreference() === "reduce";
  let observer;

  const motionToggle = $("#motion-toggle");
  function updateMotion() {
    const reduce = manuallyReduced || reducedMotion.matches;
    document.body.classList.toggle("reduce-motion", reduce);
    motionToggle.setAttribute("aria-pressed", String(reduce));
    motionToggle.textContent = reduce ? "Reduced motion on" : "Reduce motion";
    if (reduce) {
      if (observer) observer.disconnect();
      $$(".reveal").forEach((element) => element.classList.remove("pending"));
    }
  }
  motionToggle.hidden = false;
  motionToggle.addEventListener("click", () => {
    manuallyReduced = !manuallyReduced;
    try {
      localStorage.setItem(
        "aiclip-motion",
        manuallyReduced ? "reduce" : "system",
      );
    } catch (_) {
      /* Storage is optional. */
    }
    updateMotion();
  });
  if (reducedMotion.addEventListener) reducedMotion.addEventListener("change", updateMotion);
  else reducedMotion.addListener(updateMotion);
  updateMotion();

  const menu = $(".menu-button");
  const links = $("#nav-links");
  menu.hidden = false;
  function closeMenu() {
    menu.setAttribute("aria-expanded", "false");
    links.classList.remove("open");
  }
  menu.addEventListener("click", () => {
    const open = menu.getAttribute("aria-expanded") !== "true";
    menu.setAttribute("aria-expanded", String(open));
    links.classList.toggle("open", open);
  });
  links.addEventListener("click", (event) => {
    if (event.target.closest("a")) closeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (
      event.key === "Escape" &&
      menu.getAttribute("aria-expanded") === "true"
    ) {
      closeMenu();
      menu.focus();
    }
  });

  const tabs = $$('[role="tab"]');
  function selectTab(tab, focus = false) {
    tabs.forEach((item) => {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute("aria-controls")).hidden =
        !selected;
    });
    if (focus) tab.focus();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft")
        next = (index + tabs.length - 1) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next !== undefined) {
        event.preventDefault();
        selectTab(tabs[next], true);
      }
    });
  });
  selectTab(tabs[0]);
  $('[role="tablist"]').hidden = false;

  $$(".download-filter button").forEach((button) =>
    button.addEventListener("click", () => {
      $$(".download-filter button").forEach((item) =>
        item.setAttribute("aria-pressed", String(item === button)),
      );
      $$(".download-card").forEach((card) => {
        card.hidden =
          button.dataset.platform !== "all" &&
          card.dataset.os !== button.dataset.platform;
        card.classList.remove("pending");
      });
    }),
  );
  $(".download-filter").hidden = false;
  const platform =
    navigator.userAgentData?.platform || navigator.platform || "";
  if (/win/i.test(platform))
    $("#platform-hint").textContent =
      "Using Windows? Choose the Windows x64 installer.";
  else if (/mac/i.test(platform))
    $("#platform-hint").textContent =
      "Using a Mac? Check About This Mac to choose Apple Silicon or Intel.";
  else if (/linux/i.test(platform))
    $("#platform-hint").textContent =
      "Using Linux? Choose the DEB package or portable ZIP.";

  const copyButton = $("#copy-command");
  copyButton.hidden = false;
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#install-command").textContent);
      $("#copy-status").textContent = "Install command copied.";
    } catch (_) {
      $("#copy-status").textContent =
        "Clipboard unavailable. Select and copy the command above.";
    }
  });

  document.documentElement.classList.add("enhanced");
  if (
    "IntersectionObserver" in window &&
    !manuallyReduced &&
    !reducedMotion.matches
  ) {
    observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.remove("pending");
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.06 },
    );
    $$(".reveal").forEach((element) => {
      element.classList.add("pending");
      observer.observe(element);
    });
  }
})();
