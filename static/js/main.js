document.addEventListener("DOMContentLoaded", function () {
    // Remove the root SVG <title> so the browser’s native tooltip isn't used.
    const svgRoot = document.getElementById("world-map");
    if (svgRoot) {
      const rootTitle = svgRoot.querySelector("title");
      if (rootTitle) {
        rootTitle.remove();
      }
    }
    
    // Remove any native title attributes from all interactive country elements.
    document.querySelectorAll(".country").forEach(elem => {
      elem.removeAttribute("title");
      let titleElem = elem.querySelector("title");
      if (titleElem) {
        titleElem.remove();
      }
    });
  
    // Default mode is "single"
    let mode = "single";
    const selectedCountries = new Set();
    const maxSelections = { single: 1, pair: 2 };
  
    const tooltip = document.getElementById("tooltip");
    const svgMapContainer = document.getElementById("svg-map");
  
    // Toggle slider elements
    const toggleOptions = document.querySelectorAll(".toggle-option");
    const toggleSlider = document.querySelector(".toggle-slider");
  
    toggleOptions.forEach(option => {
      option.addEventListener("click", function () {
        toggleOptions.forEach(opt => opt.classList.remove("active"));
        this.classList.add("active");
        mode = this.getAttribute("data-mode");
        // Animate slider: 0% for "single", 50% for "pair"
        toggleSlider.style.left = mode === "single" ? "0%" : "50%";
        clearSelections();
      });
    });
  
    // Redirect automatically when the correct number of countries is selected.
    function checkRedirection() {
      if (selectedCountries.size === maxSelections[mode]) {
        const countriesArray = Array.from(selectedCountries);
        if (mode === "single") {
          window.location.href = "/country_detail?country_name=" + encodeURIComponent(countriesArray[0]);
        } else if (mode === "pair") {
          window.location.href = "/compare?country_A=" + encodeURIComponent(countriesArray[0]) +
                                 "&country_B=" + encodeURIComponent(countriesArray[1]);
        }
      }
    }
  
    function updateSelectedDisplay() {
      // (Optional: update a visual display of selected countries if needed)
    }
  
    function clearSelections() {
      document.querySelectorAll(".country.selected").forEach(elem => {
        elem.classList.remove("selected");
      });
      selectedCountries.clear();
      updateSelectedDisplay();
    }
  
    // Position tooltip relative to the SVG container.
    function showTooltip(evt, text) {
      tooltip.style.display = "block";
      tooltip.textContent = text;
      const containerRect = svgMapContainer.getBoundingClientRect();
      tooltip.style.left = (evt.clientX - containerRect.left + 10) + "px";
      tooltip.style.top = (evt.clientY - containerRect.top + 10) + "px";
    }
  
    function hideTooltip() {
      tooltip.style.display = "none";
    }
  
    document.querySelectorAll(".country").forEach(country => {
      country.addEventListener("mousemove", function (evt) {
        let countryName = country.getAttribute("data-name");
        showTooltip(evt, countryName);
      });
  
      country.addEventListener("mouseleave", function () {
        hideTooltip();
      });
  
      country.addEventListener("click", function (evt) {
        const target = evt.currentTarget;
        let countryName = target.getAttribute("data-name");
        if (target.classList.contains("selected")) {
          target.classList.remove("selected");
          selectedCountries.delete(countryName);
        } else {
          if (selectedCountries.size >= maxSelections[mode]) {
            alert("You can only select " + maxSelections[mode] + " country/countries in this mode.");
            return;
          }
          target.classList.add("selected");
          // Remove any inline fill attribute to let our CSS take over
          target.removeAttribute("fill");
          selectedCountries.add(countryName);
        }
        updateSelectedDisplay();
        checkRedirection();
      });
    });
  });
  
