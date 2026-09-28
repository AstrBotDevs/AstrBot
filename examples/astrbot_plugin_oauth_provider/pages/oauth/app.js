const bridge = window.AstrBotPluginPage;
const status = document.getElementById("status");
const authorization = document.getElementById("authorization");
const callback = document.getElementById("callback");
const buttons = [...document.querySelectorAll("button")];
buttons.forEach((button) => { button.disabled = true; });

await bridge.ready();
buttons.forEach((button) => {
  button.disabled = false;
  button.addEventListener("click", async () => {
    buttons.forEach((item) => { item.disabled = true; });
    status.textContent = "Working…";
    const action = button.id;
    const body = action === "complete" ? { callback_url: callback.value.trim() } : {};
    callback.value = "";
    try {
      const result = await bridge.apiPost(`oauth/${action}`, body);
      authorization.value = action === "start" ? result.authorization_url : "";
      if (action === "complete") {
        status.textContent = "Signed in. Add your models in Providers, or activate existing saved models.";
      } else if (action === "disconnect") {
        status.textContent = "Local credentials deleted. Revoke access on the supplier website when needed.";
      } else {
        status.textContent = action === "start" ? "Open the authorization URL to continue." : "Done.";
      }
    } catch (error) {
      // Never log the callback URL or send credentials to analytics.
      status.textContent = error.message || "Operation failed.";
    } finally {
      buttons.forEach((item) => { item.disabled = false; });
    }
  });
});
