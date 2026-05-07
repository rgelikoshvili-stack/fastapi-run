(function () {
  function debounce(fn, wait) {
    let timer = null;
    const delay = typeof wait === 'number' ? wait : 300;
    return function debounced() {
      const ctx = this;
      const args = arguments;
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        fn.apply(ctx, args);
      }, delay);
    };
  }

  window.BHDebounce = debounce;
})();
