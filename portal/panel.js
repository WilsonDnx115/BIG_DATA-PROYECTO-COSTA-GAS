/*
 * Portal Costa Gas · subida de entregas, estado por capa y resumen de KPI.
 *
 * B12: sube el archivo a landing/ con una URL prefirmada y muestra el recorrido por las capas,
 *      refrescando solo mientras la pestaña está visible.
 * B13: pinta los cinco KPI desde la función `kpis`.
 *
 * Se apoya en Portal.llamar() de app.js (B11), que pone el token y renueva la sesión. Aquí no
 * hay claves ni URL fijas: todas salen de config.js, que genera el despliegue.
 *
 * Tres reglas que este archivo respeta y conviene no romper al editarlo:
 *   - un indicador sin dato se muestra como «sin dato», nunca como cero;
 *   - el archivo va del navegador a S3 directamente, con PUT a la URL prefirmada: no pasa por
 *     ninguna función, así que un Excel grande no toca el límite de carga de Lambda;
 *   - lo que la función de estado no informa se dice, en vez de pintar una capa en verde.
 */
(function () {
  "use strict";

  var REFRESCO_MS = 10000;        // el estado se repinta cada 10 s (index.html lo anuncia así)
  var ESPERA_TRAS_SUBIR_MS = 2000;
  var CIFRADO = "AES256";         // la URL se firma con ServerSideEncryption=AES256

  var temporizador = null;
  var subiendo = false;

  function $(id) { return document.getElementById(id); }

  function texto(nodo, valor) { if (nodo) { nodo.textContent = valor; } }

  function pedir(funcion, cuerpo) {
    return window.Portal.llamar(funcion, "", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo || {})
    }).then(function (r) {
      return r.json().then(function (datos) {
        if (!r.ok) { throw new Error(datos && datos.error ? datos.error : "error " + r.status); }
        return datos;
      });
    });
  }

  // --- 1 · subir la entrega (B12) --------------------------------------------------------

  /** PUT del archivo a la URL prefirmada, con progreso. No lleva el token: la URL ya autoriza. */
  function subirArchivo(url, archivo, alAvanzar) {
    return new Promise(function (resolver, rechazar) {
      var peticion = new XMLHttpRequest();
      peticion.open("PUT", url, true);
      peticion.setRequestHeader("x-amz-server-side-encryption", CIFRADO);
      peticion.upload.onprogress = function (e) {
        if (e.lengthComputable) { alAvanzar(Math.round((e.loaded / e.total) * 100)); }
      };
      peticion.onload = function () {
        if (peticion.status >= 200 && peticion.status < 300) { resolver(); }
        else { rechazar(new Error("S3 respondió " + peticion.status)); }
      };
      peticion.onerror = function () { rechazar(new Error("no se pudo subir el archivo")); };
      peticion.send(archivo);
    });
  }

  function alSubir(evento) {
    evento.preventDefault();
    if (subiendo) { return; }

    var campo = $("campo-archivo");
    var archivo = campo.files && campo.files[0];
    if (!archivo) { texto($("texto-subida"), "Elige un archivo."); return; }

    var barra = $("progreso-subida");
    var aviso = $("texto-subida");
    subiendo = true;
    barra.hidden = false;
    barra.value = 0;
    texto(aviso, "Pidiendo permiso de carga…");

    pedir("firmar", { nombre: archivo.name })
      .then(function (datos) {
        texto(aviso, "Subiendo " + archivo.name + "…");
        return subirArchivo(datos.url, archivo, function (pct) {
          barra.value = pct;
          texto(aviso, "Subiendo " + archivo.name + "… " + pct + " %");
        }).then(function () { return datos; });
      })
      .then(function (datos) {
        texto(aviso, "Listo: " + datos.clave + ". El pipeline la recoge por evento; el estado de "
                     + "abajo se actualiza solo.");
        campo.value = "";
        // Da tiempo a que la Lambda de ingesta escriba su manifiesto antes de releer.
        setTimeout(refrescarEstado, ESPERA_TRAS_SUBIR_MS);
      })
      .catch(function (err) {
        texto(aviso, "No se pudo subir: " + err.message);
      })
      .then(function () {
        subiendo = false;
        barra.hidden = true;
      });
  }

  // --- 2 · estado por capa (B12) ---------------------------------------------------------

  function ultimaFecha(cargas) {
    var fechas = Object.keys(cargas || {}).sort();
    return fechas.length ? fechas[fechas.length - 1] : null;
  }

  // Los modificadores son los que ya define estilos.css: lista (verde), en-curso (ámbar), fallo (rojo).
  var CLASE_ESTADO = { ok: "capa--lista", aviso: "capa--en-curso", error: "capa--fallo" };

  function filaCapa(capa, titulo, detalle, estado) {
    var li = document.createElement("li");
    li.className = "capa" + (CLASE_ESTADO[estado] ? " " + CLASE_ESTADO[estado] : "");
    li.setAttribute("data-capa", capa);

    var nombre = document.createElement("span");
    nombre.className = "capa__nombre";
    nombre.textContent = titulo;

    var valor = document.createElement("span");
    valor.className = "capa__hora";
    valor.textContent = detalle;

    li.appendChild(nombre);
    li.appendChild(valor);
    return li;
  }

  function tablasConControl(calidad) {
    var nombres = Object.keys(calidad || {});
    var conError = nombres.filter(function (t) { return calidad[t] && calidad[t].error; });
    return { total: nombres.length, conError: conError.length };
  }

  function pintarEstado(datos) {
    var lista = $("lista-capas");
    if (!lista) { return; }
    lista.textContent = "";

    var fecha = ultimaFecha(datos.cargas_por_fecha);
    var control = tablasConControl(datos.calidad_silver);

    lista.appendChild(filaCapa("landing", "Landing",
      "la función de estado no lo informa", "sin dato"));

    lista.appendChild(filaCapa("bronze", "Bronze",
      datos.archivos_en_manifiesto
        ? datos.archivos_en_manifiesto + " archivos en el manifiesto"
          + (fecha ? " · última carga " + fecha : "")
        : "sin archivos en el manifiesto",
      datos.archivos_en_manifiesto ? "ok" : "sin dato"));

    lista.appendChild(filaCapa("silver", "Silver",
      control.total
        ? control.total + " tablas con control"
          + (control.conError ? " · " + control.conError + " ilegibles" : "")
        : "sin controles de calidad",
      control.total ? (control.conError ? "aviso" : "ok") : "sin dato"));

    lista.appendChild(filaCapa("gold", "Gold",
      "lo escribe el job de Glue; esta función no lo consulta", "sin dato"));

    if (control.total) {
      lista.appendChild(filaCapa("detalle", "Tablas de Silver",
        Object.keys(datos.calidad_silver).sort().join(", "), "ok"));
    }
  }

  function refrescarEstado() {
    if (!window.Portal.conectado()) { return Promise.resolve(); }
    return pedir("estado", {})
      .then(pintarEstado)
      .catch(function (err) {
        var lista = $("lista-capas");
        if (lista) {
          lista.textContent = "";
          lista.appendChild(filaCapa("error", "Estado",
            "no se pudo leer: " + err.message, "error"));
        }
      });
  }

  // --- 3 · resumen de KPI (B13) ----------------------------------------------------------

  var KPIS = [
    { id: "kpi_1", titulo: "KPI 1 · Diferencia no explicada" },
    { id: "kpi_2", titulo: "KPI 2 · Valor de la diferencia" },
    { id: "kpi_3", titulo: "KPI 3 · Compras con segundo registro" },
    { id: "kpi_4", titulo: "KPI 4 · Combustible por tonelada" },
    { id: "kpi_5", titulo: "KPI 5 · Confirmación documental" }
  ];

  function tarjetaKpi(titulo, valor, nota) {
    var div = document.createElement("div");
    div.className = "kpi";

    var t = document.createElement("span");
    t.className = "kpi__nombre";
    t.textContent = titulo;

    var v = document.createElement("strong");
    v.className = "kpi__valor";
    v.textContent = valor;

    div.appendChild(t);
    div.appendChild(v);

    if (nota) {
      var n = document.createElement("span");
      n.className = "kpi__nota";
      n.textContent = nota;
      div.appendChild(n);
    }
    return div;
  }

  /** Una respuesta sin filas o sin vista es «sin dato»: nunca un cero. */
  function resumirKpi(datos) {
    if (!datos || datos.estado === "sin_vista") { return { valor: "sin dato", nota: "la vista todavía no está desplegada" }; }
    if (datos.estado !== "ok") { return { valor: "sin dato", nota: datos.motivo || datos.estado }; }
    if (!datos.n_filas) { return { valor: "sin dato", nota: "la vista no devolvió filas" }; }
    return { valor: datos.n_filas + " filas", nota: "en " + datos.vista };
  }

  function refrescarKpis() {
    var caja = $("lista-kpis");
    if (!caja || !window.Portal.conectado()) { return Promise.resolve(); }
    caja.textContent = "";

    return Promise.all(KPIS.map(function (k) {
      return pedir("kpis", { indicador: k.id })
        .then(function (datos) { return { k: k, r: resumirKpi(datos) }; })
        .catch(function (err) { return { k: k, r: { valor: "sin dato", nota: err.message } }; });
    })).then(function (resultados) {
      resultados.forEach(function (x) {
        caja.appendChild(tarjetaKpi(x.k.titulo, x.r.valor, x.r.nota));
      });
    });
  }

  // --- 4 · refresco automático -----------------------------------------------------------

  function visible() {
    return document.visibilityState !== "hidden";
  }

  function arrancarRefresco() {
    detenerRefresco();
    refrescarEstado();
    refrescarKpis();
    temporizador = setInterval(function () {
      // Con la pestaña oculta no se consulta: cada llamada a `kpis` es una consulta de Athena.
      if (visible() && window.Portal.conectado()) { refrescarEstado(); }
    }, REFRESCO_MS);
  }

  function detenerRefresco() {
    if (temporizador) { clearInterval(temporizador); temporizador = null; }
  }

  function arrancar() {
    var formulario = $("form-subir");
    if (formulario) { formulario.addEventListener("submit", alSubir); }

    document.addEventListener("portal:sesion", function (e) {
      if (e.detail && e.detail.conectado) { arrancarRefresco(); } else { detenerRefresco(); }
    });
    document.addEventListener("visibilitychange", function () {
      if (visible() && window.Portal.conectado()) { refrescarEstado(); }
    });

    if (window.Portal && window.Portal.conectado()) { arrancarRefresco(); }
  }

  window.PortalPanel = {
    refrescarEstado: refrescarEstado,
    refrescarKpis: refrescarKpis,
    resumirKpi: resumirKpi,
    ultimaFecha: ultimaFecha
  };

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", arrancar); }
  else { arrancar(); }
})();
