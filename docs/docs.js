// Copy buttons for the docs page. Buttons carry data-copy="<id of the element to copy>".
for (const button of document.querySelectorAll("button[data-copy]")) {
  button.addEventListener("click", async () => {
    const source = document.getElementById(button.dataset.copy);
    if (!source) return;
    const label = button.textContent;
    try {
      await navigator.clipboard.writeText(source.textContent.trim());
      button.textContent = "Copied";
    } catch {
      // Clipboard access can be blocked (insecure origin, iframe). Select the text so Ctrl+C works.
      const range = document.createRange();
      range.selectNodeContents(source);
      const selection = getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = "Press Ctrl+C";
    }
    setTimeout(() => { button.textContent = label; }, 1800);
  });
}
