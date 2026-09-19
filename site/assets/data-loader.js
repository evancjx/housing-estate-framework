(() => {
  "use strict";

  const DEFAULT_TIMEOUT_MS = 12_000;
  const MAX_CACHE_ENTRIES = 16;
  const successful = new Map();
  const inFlight = new Map();

  class DataLoadError extends Error {
    constructor(kind, message, { url = "", status = null, cause = null } = {}) {
      super(message);
      this.name = "DataLoadError";
      this.kind = kind;
      this.url = url;
      this.status = status;
      if (cause) this.cause = cause;
    }
  }

  function baseURL(options = {}) {
    return options.baseURL
      || globalThis.document?.baseURI
      || globalThis.location?.href
      || "http://localhost/";
  }

  function resolveURL(path, options = {}) {
    if (
      !(typeof path === "string" || path instanceof URL)
      || !String(path).trim()
    ) {
      throw new DataLoadError("url", "The data source URL is missing or invalid.");
    }
    try {
      const url = new URL(String(path), baseURL(options));
      if (options.revision) url.searchParams.set("v", String(options.revision));
      return url.href;
    } catch (cause) {
      throw new DataLoadError("url", "The data source URL is invalid.", { cause });
    }
  }

  function remember(url, value) {
    successful.delete(url);
    successful.set(url, value);
    while (successful.size > MAX_CACHE_ENTRIES) {
      successful.delete(successful.keys().next().value);
    }
  }

  function cached(url) {
    if (!successful.has(url)) return undefined;
    const value = successful.get(url);
    successful.delete(url);
    successful.set(url, value);
    return value;
  }

  function validatePayload(value, validate, url) {
    if (typeof validate !== "function") return value;
    try {
      const result = validate(value);
      if (result === false) {
        throw new TypeError("The data source has an unexpected shape.");
      }
      if (typeof result === "string" && result) throw new TypeError(result);
      return value;
    } catch (cause) {
      if (cause instanceof DataLoadError) throw cause;
      throw new DataLoadError(
        "schema",
        cause instanceof Error && cause.message
          ? cause.message
          : "The data source has an unexpected shape.",
        { url, cause }
      );
    }
  }

  async function requestJSON(url, options) {
    const controller = new AbortController();
    const callerSignal = options.signal;
    let timedOut = false;
    let callerAborted = Boolean(callerSignal?.aborted);
    const abortFromCaller = () => {
      callerAborted = true;
      controller.abort(callerSignal?.reason);
    };
    if (callerSignal && !callerSignal.aborted) {
      callerSignal.addEventListener("abort", abortFromCaller, { once: true });
    }
    if (callerAborted) controller.abort(callerSignal?.reason);

    const requestedTimeout = Number(options.timeoutMs);
    const timeoutMs = Number.isFinite(requestedTimeout) && requestedTimeout > 0
      ? requestedTimeout
      : DEFAULT_TIMEOUT_MS;
    const timer = globalThis.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);

    try {
      let response;
      try {
        response = await globalThis.fetch(url, {
          cache: "default",
          credentials: "same-origin",
          headers: { Accept: "application/json", ...(options.headers || {}) },
          signal: controller.signal,
        });
      } catch (cause) {
        if (timedOut) {
          throw new DataLoadError(
            "timeout",
            `The data source did not respond within ${timeoutMs} ms.`,
            { url, cause }
          );
        }
        if (callerAborted || controller.signal.aborted) {
          throw new DataLoadError("aborted", "The data request was cancelled.", {
            url,
            cause,
          });
        }
        throw new DataLoadError("network", "The data source could not be reached.", {
          url,
          cause,
        });
      }

      if (!response?.ok) {
        const status = Number.isFinite(Number(response?.status))
          ? Number(response.status)
          : null;
        throw new DataLoadError(
          "http",
          status === null
            ? "The data source returned an unsuccessful response."
            : `The data source returned HTTP ${status}.`,
          { url, status }
        );
      }

      try {
        return await response.json();
      } catch (cause) {
        throw new DataLoadError("parse", "The data source did not contain valid JSON.", {
          url,
          cause,
        });
      }
    } finally {
      globalThis.clearTimeout(timer);
      callerSignal?.removeEventListener?.("abort", abortFromCaller);
    }
  }

  async function loadJSON(path, options = {}) {
    const url = resolveURL(path, options);
    const cachedValue = cached(url);
    if (cachedValue !== undefined) {
      try {
        return validatePayload(cachedValue, options.validate, url);
      } catch (error) {
        successful.delete(url);
        throw error;
      }
    }

    let request = inFlight.get(url);
    if (!request) {
      request = requestJSON(url, options).finally(() => {
        if (inFlight.get(url) === request) inFlight.delete(url);
      });
      inFlight.set(url, request);
    }

    const value = await request;
    validatePayload(value, options.validate, url);
    remember(url, value);
    return value;
  }

  function invalidate(path, options = {}) {
    const url = resolveURL(path, options);
    return successful.delete(url);
  }

  function loadMany(resources, options = {}) {
    if (!Array.isArray(resources)) {
      return Promise.resolve([
        {
          status: "rejected",
          reason: new DataLoadError("schema", "Data resources must be an array."),
        },
      ]);
    }
    const requests = resources.map(resource => {
      if (typeof resource === "string") return loadJSON(resource, options);
      const specification = resource && typeof resource === "object" ? resource : {};
      const { path, url, ...resourceOptions } = specification;
      return loadJSON(path || url, { ...options, ...resourceOptions });
    });
    return Promise.allSettled(requests);
  }

  globalThis.SGEstateData = Object.freeze({
    DataLoadError,
    loadJSON,
    loadMany,
    invalidate,
    resolveURL,
  });
})();
