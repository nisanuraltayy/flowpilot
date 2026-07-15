import "@testing-library/jest-dom/vitest";

// React 19 form action'ları, submit'i CANCELABLE bir submit event'i ile ele
// alır ve preventDefault eder. jsdom'un requestSubmit'i bazı durumlarda native
// submit'e düşerek React'in "unexpectedly submitted" guard'ını tetikler. Bu
// polyfill, React'in yakalayabileceği düzgün bir submit event'i dispatch eder.
if (typeof HTMLFormElement !== "undefined") {
  HTMLFormElement.prototype.requestSubmit = function requestSubmit(
    this: HTMLFormElement,
    submitter?: HTMLElement | null,
  ) {
    const event = new Event("submit", { bubbles: true, cancelable: true });
    if (submitter) {
      Object.defineProperty(event, "submitter", { value: submitter, configurable: true });
    }
    this.dispatchEvent(event);
  };
}
