/*
 * Portal Costa Gas · lógica del navegador.
 *
 * B11: inicio de sesión SRP con Cognito (amazon-cognito-identity-js 6.3.12, cargada en
 * index.html desde jsDelivr con versión exacta e integridad SRI).
 *   - Los tokens viven en sessionStorage (nunca en localStorage): se borran al cerrar la pestaña.
 *   - El token de identidad se renueva con el token de actualización antes de vencer.
 *   - Cada llamada a las funciones lleva «Authorization: Bearer <token de identidad>».
 *   - No hay claves en este archivo: región, grupo de usuarios, cliente y URL de las funciones
 *     vienen de config.js, que genera infra/scripts/deploy.sh (W22) y no se versiona.
 *
 * B12 (subida y estado) y B13 (KPI y revisión) se agregan sobre Portal.llamar().
 */
(function () {
  "use strict";

  var RENOVAR_ANTES_S = 5 * 60;   // renovar el token 5 minutos antes de que venza
  var MINIMO_ESPERA_S = 30;

  var config = window.COSTAGAS || null;
  var grupo = null;
  var usuarioCognito = null;
  var sesion = null;
  var temporizador = null;
  var pendienteClaveNueva = null;

  // --- utilidades de la página ----------------------------------------------------------

  function $(id) { return document.getElementById(id); }

  function mostrarAviso(texto) {
    var aviso = $("aviso");
    aviso.textContent = texto;
    aviso.hidden = !texto;
  }

  function mostrarError(texto) {
    var error = $("error-sesion");
    error.textContent = texto || "";
    error.hidden = !texto;
  }

  function mensajeCognito(err) {
    var codigo = (err && (err.code || err.name)) || "";
    if (codigo === "NotAuthorizedException") { return "Usuario o contraseña incorrectos."; }
    if (codigo === "UserNotFoundException") { return "Usuario o contraseña incorrectos."; }
    if (codigo === "PasswordResetRequiredException") { return "Debes restablecer tu contraseña: pídelo al titular del proyecto."; }
    if (codigo === "InvalidPasswordException") { return "La contraseña no cumple la política (mínimo 12 caracteres, con mayúsculas, minúsculas y números)."; }
    if (codigo === "TooManyRequestsException" || codigo === "LimitExceededException") { return "Demasiados intentos. Espera unos minutos."; }
    return "No se pudo iniciar sesión. Inténtalo de nuevo.";
  }

  function secciones() {
    return document.querySelectorAll("main > section");
  }

  function pintarSesion(conectado) {
    $("sesion").hidden = conectado;
    $("menu").hidden = !conectado;
    $("usuario").hidden = !conectado;
    Array.prototype.forEach.call(secciones(), function (s) {
      if (s.id !== "sesion") { s.hidden = !conectado; }
    });
    if (conectado) {
      var nombre = sesion && sesion.getIdToken().decodePayload()["cognito:username"];
      $("usuario-nombre").textContent = nombre || "";
      marcarMenu();
    } else {
      $("usuario-nombre").textContent = "";
      $("form-sesion").hidden = false;
      $("form-clave-nueva").hidden = true;
    }
  }

  function marcarMenu() {
    var actual = (location.hash || "").split("/")[0];
    Array.prototype.forEach.call(document.querySelectorAll("#menu a"), function (a) {
      if (a.getAttribute("href") === actual) { a.setAttribute("aria-current", "page"); }
      else { a.removeAttribute("aria-current"); }
    });
  }

  // --- sesión y tokens ------------------------------------------------------------------

  function vencimientoS(s) {
    return s.getIdToken().getExpiration();   // segundos desde epoch
  }

  function programarRenovacion() {
    clearTimeout(temporizador);
    if (!sesion) { return; }
    var faltan = vencimientoS(sesion) - Math.floor(Date.now() / 1000) - RENOVAR_ANTES_S;
    temporizador = setTimeout(function () {
      renovar().catch(function () { cerrarSesion("Tu sesión venció. Vuelve a iniciar sesión."); });
    }, Math.max(faltan, MINIMO_ESPERA_S) * 1000);
  }

  function aceptarSesion(s) {
    sesion = s;
    pendienteClaveNueva = null;
    $("campo-clave").value = "";
    $("campo-clave-nueva").value = "";
    mostrarError("");
    mostrarAviso("");
    programarRenovacion();
    pintarSesion(true);
    document.dispatchEvent(new CustomEvent("portal:sesion", { detail: { conectado: true } }));
  }

  function renovar() {
    return new Promise(function (resolver, rechazar) {
      if (!usuarioCognito || !sesion) { rechazar(new Error("sin sesión")); return; }
      usuarioCognito.refreshSession(sesion.getRefreshToken(), function (err, nueva) {
        if (err) { rechazar(err); return; }
        sesion = nueva;
        programarRenovacion();
        resolver(nueva);
      });
    });
  }

  /** Token de identidad vigente; lo renueva si le quedan menos de 5 minutos. */
  function tokenVigente() {
    if (!sesion) { return Promise.reject(new Error("sin sesión")); }
    var quedan = vencimientoS(sesion) - Math.floor(Date.now() / 1000);
    if (quedan > RENOVAR_ANTES_S) { return Promise.resolve(sesion.getIdToken().getJwtToken()); }
    return renovar().then(function (s) { return s.getIdToken().getJwtToken(); });
  }

  function callbacksAutenticacion() {
    return {
      onSuccess: function (s) { aceptarSesion(s); habilitar(true); },
      onFailure: function (err) { mostrarError(mensajeCognito(err)); habilitar(true); },
      newPasswordRequired: function () {
        // Usuario creado por el titular: Cognito pide una contraseña propia en el primer ingreso.
        pendienteClaveNueva = usuarioCognito;
        $("campo-clave").value = "";
        $("form-sesion").hidden = true;
        $("form-clave-nueva").hidden = false;
        mostrarError("");
        habilitar(true);
        $("campo-clave-nueva").focus();
      }
    };
  }

  function habilitar(si) {
    Array.prototype.forEach.call(document.querySelectorAll("#sesion button"), function (b) {
      b.disabled = !si;
    });
  }

  function iniciarSesion(evento) {
    evento.preventDefault();
    var nombre = $("campo-usuario").value.trim();
    var clave = $("campo-clave").value;
    if (!nombre || !clave) { mostrarError("Escribe tu usuario y tu contraseña."); return; }
    habilitar(false);
    mostrarError("");
    usuarioCognito = new AmazonCognitoIdentity.CognitoUser({
      Username: nombre, Pool: grupo, Storage: window.sessionStorage
    });
    usuarioCognito.setAuthenticationFlowType("USER_SRP_AUTH");
    usuarioCognito.authenticateUser(
      new AmazonCognitoIdentity.AuthenticationDetails({ Username: nombre, Password: clave }),
      callbacksAutenticacion());
  }

  function guardarClaveNueva(evento) {
    evento.preventDefault();
    var nueva = $("campo-clave-nueva").value;
    if (!pendienteClaveNueva) { pintarSesion(false); return; }
    if (nueva.length < 12) { mostrarError("La contraseña nueva debe tener al menos 12 caracteres."); return; }
    habilitar(false);
    pendienteClaveNueva.completeNewPasswordChallenge(nueva, {}, callbacksAutenticacion());
  }

  function cerrarSesion(motivo) {
    clearTimeout(temporizador);
    if (usuarioCognito) { usuarioCognito.signOut(); }   // borra los tokens de sessionStorage
    usuarioCognito = null;
    sesion = null;
    pendienteClaveNueva = null;
    pintarSesion(false);
    mostrarAviso(typeof motivo === "string" ? motivo : "");
    document.dispatchEvent(new CustomEvent("portal:sesion", { detail: { conectado: false } }));
  }

  /** Recupera la sesión guardada en sessionStorage al recargar la pestaña. */
  function recuperarSesion() {
    var guardado = grupo.getCurrentUser();
    if (!guardado) { pintarSesion(false); return; }
    guardado.getSession(function (err, s) {
      if (err || !s || !s.isValid()) { guardado.signOut(); pintarSesion(false); return; }
      usuarioCognito = guardado;
      aceptarSesion(s);
    });
  }

  // --- llamadas a las funciones del portal ---------------------------------------------

  /**
   * Llama a una función del portal (firmar, estado, kpis o revision) con el token.
   * `ruta` se agrega a la URL de la función (por ejemplo "?semana=48"); `opciones` son las de fetch.
   * Un 401 renueva el token una vez y reintenta; si vuelve a fallar, cierra la sesión.
   */
  function llamar(funcion, ruta, opciones) {
    var base = config && config.funciones && config.funciones[funcion];
    if (!base) { return Promise.reject(new Error("función no configurada: " + funcion)); }
    var url = base.replace(/\/+$/, "") + "/" + String(ruta || "").replace(/^\/+/, "");

    function enviar(token) {
      var o = Object.assign({}, opciones || {});
      o.headers = Object.assign({}, o.headers || {}, { Authorization: "Bearer " + token });
      o.credentials = "omit";
      o.cache = "no-store";
      return fetch(url, o);
    }

    return tokenVigente()
      .then(enviar)
      .then(function (r) {
        if (r.status !== 401) { return r; }
        return renovar()
          .then(function (s) { return enviar(s.getIdToken().getJwtToken()); })
          .then(function (r2) {
            if (r2.status === 401) { cerrarSesion("Tu sesión venció. Vuelve a iniciar sesión."); }
            return r2;
          });
      })
      .catch(function (err) {
        if (!sesion) { cerrarSesion("Inicia sesión para continuar."); }
        throw err;
      });
  }

  // --- arranque -------------------------------------------------------------------------

  function configuracionValida(c) {
    return c && c.region && c.cognito && c.cognito.grupoUsuarios && c.cognito.cliente && c.funciones;
  }

  function arrancar() {
    window.addEventListener("hashchange", marcarMenu);
    if (!window.AmazonCognitoIdentity) {
      mostrarAviso("No se pudo cargar la librería de inicio de sesión. Revisa tu conexión y recarga la página.");
      habilitar(false);
      return;
    }
    if (!configuracionValida(config)) {
      mostrarAviso("El portal no está configurado (falta config.js). Lo genera el despliegue del stack.");
      habilitar(false);
      return;
    }
    grupo = new AmazonCognitoIdentity.CognitoUserPool({
      UserPoolId: config.cognito.grupoUsuarios,
      ClientId: config.cognito.cliente,
      Storage: window.sessionStorage
    });
    $("form-sesion").addEventListener("submit", iniciarSesion);
    $("form-clave-nueva").addEventListener("submit", guardarClaveNueva);
    $("boton-salir").addEventListener("click", function () { cerrarSesion(""); });
    recuperarSesion();
  }

  window.Portal = {
    llamar: llamar,
    cerrarSesion: cerrarSesion,
    conectado: function () { return !!sesion; },
    usuario: function () { return sesion ? sesion.getIdToken().decodePayload()["cognito:username"] : null; },
    mostrarAviso: mostrarAviso
  };

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", arrancar); }
  else { arrancar(); }
})();
