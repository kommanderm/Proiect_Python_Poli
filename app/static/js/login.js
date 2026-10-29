const registerForm = document.getElementById("register-form");
const loginForm = document.getElementById("login-form");
const errorBox = document.getElementById("error");

function onSubmit(form, handler) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.textContent = "";
    try {
      await handler(Object.fromEntries(new FormData(form)));
    } catch (error) {
      errorBox.textContent = error.message;
    }
  });
}

onSubmit(registerForm, async (fields) => {
  const user = await api("/api/register", { method: "POST", body: fields });
  document.getElementById("new-id").textContent = user.id;
  document.getElementById("registered").hidden = false;
  registerForm.hidden = true;
  loginForm.hidden = true;
});

onSubmit(loginForm, async (fields) => {
  await api("/api/login", { method: "POST", body: fields });
  location.href = "/";
});
