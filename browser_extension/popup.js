let currentUrl = "";

const pageLabel = document.getElementById("page");
const statusLabel = document.getElementById("status");
const sendButton = document.getElementById("send");
const copyButton = document.getElementById("copy");

chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  currentUrl = tabs[0]?.url ?? "";
  const supported = /^https?:\/\//i.test(currentUrl);
  pageLabel.textContent = supported ? currentUrl : "This page has no downloadable web URL.";
  sendButton.disabled = !supported;
  copyButton.disabled = !supported;
});

sendButton.addEventListener("click", () => {
  if (!currentUrl) return;
  const handoff = `udown://download?url=${encodeURIComponent(currentUrl)}`;
  window.location.href = handoff;
  statusLabel.textContent = "Opening the desktop app...";
});

copyButton.addEventListener("click", async () => {
  if (!currentUrl) return;
  try {
    await navigator.clipboard.writeText(currentUrl);
    statusLabel.textContent = "Page URL copied.";
  } catch {
    statusLabel.textContent = "Could not copy the page URL.";
  }
});