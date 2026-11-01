try {
  var stored = localStorage.getItem("color-scheme");
  if (stored === "light" || stored === "dark") {
    document.querySelector('meta[name="color-scheme"]').content = stored;
  }
} catch (e) {}
