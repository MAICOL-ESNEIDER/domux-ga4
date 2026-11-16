/*
 * Comportamientos pequeños de la web de administración. Todo funciona también sin este archivo
 * (los formularios se envían igual); aquí solo se agregan comodidades: el menú del celular, la
 * confirmación antes de una acción delicada, el botón «Filtros», cerrar un aviso, la selección
 * de varias filas y el foco en el detalle que se abre. Va como archivo aparte porque la política de seguridad no admite scripts dentro
 * de la página.
 */
(function () {
  "use strict";

  var root = document.documentElement;
  root.classList.add("js");

  // --- Menú ☰ en pantallas angostas ---------------------------------------------------------------
  var menuButton = document.querySelector("[data-menu-toggle]");

  function setMenu(open) {
    root.classList.toggle("menu-open", open);
    if (menuButton) {
      menuButton.setAttribute("aria-expanded", open ? "true" : "false");
    }
  }

  if (menuButton) {
    menuButton.addEventListener("click", function () {
      setMenu(!root.classList.contains("menu-open"));
    });
  }

  document.addEventListener("click", function (event) {
    if (!root.classList.contains("menu-open")) {
      return;
    }
    if (event.target.closest(".sidebar") || event.target.closest("[data-menu-toggle]")) {
      return;
    }
    setMenu(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      setMenu(false);
    }
  });

  // --- Confirmación antes de una acción delicada --------------------------------------------------
  // <form data-confirm="¿Seguro?"> o <button data-confirm="..." data-confirm-label="Retirar">.
  function askConfirmation(message, label, danger, onAccept) {
    if (!window.HTMLDialogElement) {
      if (window.confirm(message)) {
        onAccept();
      }
      return;
    }
    var dialog = document.createElement("dialog");
    dialog.setAttribute("aria-label", "Confirmar acción");

    var text = document.createElement("p");
    text.textContent = message;
    dialog.appendChild(text);

    var actions = document.createElement("div");
    actions.className = "dialog-actions";

    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn btn-quiet";
    cancel.textContent = "Cancelar";
    cancel.addEventListener("click", function () {
      dialog.close();
    });

    var accept = document.createElement("button");
    accept.type = "button";
    accept.className = danger ? "btn btn-danger" : "btn";
    accept.textContent = label || "Confirmar";
    accept.addEventListener("click", function () {
      dialog.close();
      onAccept();
    });

    actions.appendChild(cancel);
    actions.appendChild(accept);
    dialog.appendChild(actions);
    dialog.addEventListener("close", function () {
      dialog.remove();
    });
    document.body.appendChild(dialog);
    dialog.showModal();
    cancel.focus();
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    var submitter = event.submitter;
    var source = (submitter && submitter.dataset.confirm) ? submitter : form;
    var message = source.dataset.confirm;
    if (form.dataset.confirmed === "1") {
      delete form.dataset.confirmed;
      return;
    }
    if (!message) {
      return;
    }
    event.preventDefault();
    askConfirmation(message, source.dataset.confirmLabel, source.dataset.confirmDanger !== "no", function () {
      form.dataset.confirmed = "1";
      if (form.requestSubmit) {
        form.requestSubmit(submitter || undefined);
      } else {
        form.submit();
      }
    });
  });

  // --- Campos que solo aplican a un rol -----------------------------------------------------------
  // <select data-role-select> y bloques <div data-role-only="RESIDENT">: el bloque se esconde si el
  // rol elegido es otro. Sin JavaScript se ven todos y el servidor ignora los que no corresponden.
  var roleSelect = document.querySelector("[data-role-select]");
  if (roleSelect) {
    var refreshRoleFields = function () {
      document.querySelectorAll("[data-role-only]").forEach(function (block) {
        block.hidden = block.dataset.roleOnly.split(" ").indexOf(roleSelect.value) === -1;
      });
    };
    roleSelect.addEventListener("change", refreshRoleFields);
    refreshRoleFields();
  }

  // --- Filtros que se aplican al cambiar ------------------------------------------------------------
  // <select data-autosubmit> dentro de un formulario GET.
  document.addEventListener("change", function (event) {
    var field = event.target;
    if (field.matches && field.matches("[data-autosubmit]") && field.form) {
      field.form.submit();
    }
  });

  // --- Botón «Filtros» ---------------------------------------------------------------------------
  // <button data-filters-toggle aria-controls="panel"> abre y cierra el panel de filtros sin recargar
  // la página (sin JavaScript, el mismo botón la recarga con el panel abierto).
  function setFilters(button, panel, open) {
    panel.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  document.querySelectorAll("[data-filters-toggle]").forEach(function (button) {
    var panel = document.getElementById(button.getAttribute("aria-controls"));
    if (!panel) {
      return;
    }
    button.addEventListener("click", function (event) {
      event.preventDefault();
      var open = panel.hidden;
      setFilters(button, panel, open);
      if (open) {
        var first = panel.querySelector("select, input, textarea");
        if (first) {
          first.focus();
        }
      }
    });
    panel.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        setFilters(button, panel, false);
        button.focus();
      }
    });
  });

  // --- Cerrar un aviso -------------------------------------------------------------------------------
  document.addEventListener("click", function (event) {
    var close = event.target.closest && event.target.closest("[data-dismiss-notice]");
    if (close) {
      var notice = close.closest(".notice");
      if (notice) {
        notice.remove();
      }
    }
  });

  // --- Selección de varias filas ----------------------------------------------------------------------
  // <input type="checkbox" data-select-all="grupo"> marca o desmarca las filas
  // <input type="checkbox" data-select-item="grupo">; <span data-select-count="grupo"> muestra cuántas
  // hay marcadas y <button data-needs-selection="grupo"> solo se habilita con al menos una.
  function refreshSelection(group) {
    var items = document.querySelectorAll('[data-select-item="' + group + '"]');
    var checked = 0;
    items.forEach(function (item) {
      if (item.checked) {
        checked += 1;
      }
      var row = item.closest("tr, [data-select-row]");
      if (row) {
        row.classList.toggle("is-selected", item.checked);
      }
    });
    document.querySelectorAll('[data-select-count="' + group + '"]').forEach(function (label) {
      label.textContent = String(checked);
    });
    document.querySelectorAll('[data-needs-selection="' + group + '"]').forEach(function (button) {
      button.disabled = checked === 0;
    });
    var all = document.querySelector('[data-select-all="' + group + '"]');
    if (all) {
      all.checked = items.length > 0 && checked === items.length;
    }
  }

  document.addEventListener("change", function (event) {
    var field = event.target;
    if (!field.dataset) {
      return;
    }
    if (field.dataset.selectAll) {
      var group = field.dataset.selectAll;
      document.querySelectorAll('[data-select-item="' + group + '"]').forEach(function (item) {
        item.checked = field.checked;
      });
      refreshSelection(group);
    } else if (field.dataset.selectItem) {
      refreshSelection(field.dataset.selectItem);
    }
  });

  document.querySelectorAll("[data-select-all]").forEach(function (all) {
    refreshSelection(all.dataset.selectAll);
  });

  // --- Foco al abrir el detalle -----------------------------------------------------------------------
  // <h2 tabindex="-1" data-focus-on-load>: al abrir una solicitud, el teclado y el lector de pantalla
  // quedan en su título y no al comienzo de la página.
  var focusTarget = document.querySelector("[data-focus-on-load]");
  if (focusTarget) {
    focusTarget.focus();
  }

  // --- Cuentas recientes en este equipo ---------------------------------------------------------------
  // Si al entrar se marca «Recordar mi correo en este equipo», este navegador guarda el correo y el
  // nombre (nunca la contraseña). En el inicio de sesión salen como una lista para tocar la cuenta y
  // escribir solo la contraseña; cada una se quita con su X. El servidor no guarda ninguna lista.
  var ACCOUNTS_KEY = "domux.cuentasRecientes";
  var MAX_ACCOUNTS = 5;

  function storageWorks() {
    try {
      var probe = ACCOUNTS_KEY + ".prueba";
      window.localStorage.setItem(probe, "1");
      window.localStorage.removeItem(probe);
      return true;
    } catch (error) {
      return false;
    }
  }

  function sameEmail(first, second) {
    return String(first || "").trim().toLowerCase() === String(second || "").trim().toLowerCase();
  }

  function readAccounts() {
    try {
      var list = JSON.parse(window.localStorage.getItem(ACCOUNTS_KEY) || "[]");
      if (!Array.isArray(list)) {
        return [];
      }
      return list.filter(function (item) {
        return item && typeof item.correo === "string" && item.correo.indexOf("@") > 0;
      }).slice(0, MAX_ACCOUNTS);
    } catch (error) {
      return [];
    }
  }

  function writeAccounts(list) {
    try {
      if (list.length) {
        window.localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(list.slice(0, MAX_ACCOUNTS)));
      } else {
        window.localStorage.removeItem(ACCOUNTS_KEY);
      }
    } catch (error) {
      // Navegador en modo privado o sin espacio: la lista no se guarda y el ingreso sigue igual.
    }
  }

  function initialsOf(name, email) {
    var source = String(name || "").trim() || String(email || "").split("@")[0];
    var words = source.split(/[\s._-]+/).filter(Boolean);
    var letters = words.length > 1 ? words[0].charAt(0) + words[1].charAt(0) : source.slice(0, 2);
    return letters.toUpperCase();
  }

  // Primera página después de entrar con la casilla marcada: guarda la cuenta al comienzo de la lista.
  var accountToRemember = document.querySelector("[data-recordar-cuenta]");
  if (accountToRemember && storageWorks()) {
    var rememberedEmail = accountToRemember.dataset.correo;
    var others = readAccounts().filter(function (item) {
      return !sameEmail(item.correo, rememberedEmail);
    });
    writeAccounts([{ correo: rememberedEmail, nombre: accountToRemember.dataset.nombre || "" }].concat(others));
    accountToRemember.remove();
  }

  var loginForm = document.querySelector("[data-login-form]");
  if (loginForm && storageWorks()) {
    var accountsBox = document.querySelector("[data-cuentas]");
    var accountsList = document.querySelector("[data-cuentas-lista]");
    var accountTemplate = document.querySelector("[data-cuenta-plantilla]");
    var removedNotice = document.querySelector("[data-cuenta-quitada]");
    var removedText = document.querySelector("[data-cuenta-quitada-texto]");
    var chosenBox = loginForm.querySelector("[data-cuenta-elegida]");
    var emailField = loginForm.querySelector("[data-campo-correo]");
    var emailInput = loginForm.querySelector("input[name='email']");
    var passwordInput = loginForm.querySelector("input[name='password']");
    var rememberField = loginForm.querySelector("[data-campo-recordar]");
    var rememberInput = loginForm.querySelector("input[name='recordar']");
    var backButton = loginForm.querySelector("[data-volver-cuentas]");
    var lastRemoved = null;

    var hideRemovedNotice = function () {
      removedNotice.hidden = true;
      lastRemoved = null;
    };

    // Formulario de siempre (account = null) o con una cuenta de la lista ya elegida.
    var showForm = function (account, moveFocus) {
      accountsBox.hidden = true;
      loginForm.hidden = false;
      chosenBox.hidden = !account;
      emailField.hidden = !!account;
      rememberField.hidden = !!account;
      backButton.hidden = readAccounts().length === 0;
      if (account) {
        emailInput.value = account.correo;
        // Entrar con una cuenta de la lista la vuelve a guardar de primera, con el nombre al día.
        rememberInput.checked = true;
        chosenBox.querySelector("[data-elegida-iniciales]").textContent = initialsOf(account.nombre, account.correo);
        chosenBox.querySelector("[data-elegida-nombre]").textContent = account.nombre || account.correo;
        chosenBox.querySelector("[data-elegida-correo]").textContent = account.correo;
        if (moveFocus) {
          passwordInput.focus();
        }
      } else {
        rememberInput.checked = false;
        if (moveFocus) {
          emailInput.focus();
        }
      }
    };

    var showList = function (moveFocus) {
      var accounts = readAccounts();
      if (!accounts.length) {
        showForm(null, moveFocus);
        return;
      }
      accountsList.textContent = "";
      accounts.forEach(function (account) {
        var item = accountTemplate.content.firstElementChild.cloneNode(true);
        item.querySelector("[data-iniciales]").textContent = initialsOf(account.nombre, account.correo);
        item.querySelector("[data-nombre]").textContent = account.nombre || account.correo;
        item.querySelector("[data-correo]").textContent = account.correo;
        item.querySelector("[data-quitar-texto]").textContent = "Quitar " + account.correo + " de este equipo";
        item.querySelector("[data-elegir]").addEventListener("click", function () {
          hideRemovedNotice();
          showForm(account, true);
        });
        item.querySelector("[data-quitar]").addEventListener("click", function () {
          removeAccount(account);
        });
        accountsList.appendChild(item);
      });
      emailInput.value = "";
      loginForm.hidden = true;
      accountsBox.hidden = false;
      if (moveFocus) {
        accountsList.querySelector("[data-elegir]").focus();
      }
    };

    var removeAccount = function (account) {
      writeAccounts(readAccounts().filter(function (item) {
        return !sameEmail(item.correo, account.correo);
      }));
      lastRemoved = account;
      removedText.textContent = "Se quitó " + account.correo + " de este equipo.";
      removedNotice.hidden = false;
      showList(true);
    };

    removedNotice.querySelector("[data-deshacer-quitar]").addEventListener("click", function () {
      if (lastRemoved) {
        var restored = lastRemoved;
        writeAccounts([restored].concat(readAccounts().filter(function (item) {
          return !sameEmail(item.correo, restored.correo);
        })));
      }
      hideRemovedNotice();
      showList(true);
    });

    accountsBox.querySelector("[data-usar-otra]").addEventListener("click", function () {
      hideRemovedNotice();
      emailInput.value = "";
      showForm(null, true);
    });

    chosenBox.querySelector("[data-cambiar-cuenta]").addEventListener("click", function () {
      showList(true);
    });

    backButton.addEventListener("click", function () {
      showList(true);
    });

    // Al abrir: si volvió con un error, se queda en el formulario (con la cuenta si era de la lista);
    // si hay cuentas guardadas, primero la lista; si no, el formulario de siempre.
    rememberField.hidden = false;
    var typedEmail = emailInput.value.trim();
    if (typedEmail) {
      var known = readAccounts().filter(function (item) {
        return sameEmail(item.correo, typedEmail);
      })[0];
      showForm(known || null, false);
    } else {
      showList(false);
    }
  }
})();
