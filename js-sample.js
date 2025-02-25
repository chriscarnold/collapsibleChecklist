$(document).ready(function() {
    // Initialize collapsible sections
    function initCollapsible() {
        $('.checklist .container.collapsible').each(function() {
            var $container = $(this);
            
            // Handle click events
            $container.on('click', function(e) {
                // Don't trigger if clicking checkbox or selecting text in code block
                if ($(e.target).is('input[type="checkbox"]') || 
                    $(e.target).is('pre') ||
                    window.getSelection().toString()) {
                    return;
                }
                
                // Toggle active class and slide pre tags
                $(this).toggleClass('active');
                $(this).find('pre').slideToggle(200);
                
                // Prevent event from bubbling up
                e.stopPropagation();
            });
            
            // Initially hide code blocks
            $container.find('pre').hide();
        });
    }

    // Run initialization when page loads
    initCollapsible();
    
    // Re-run when content is dynamically updated
    $(document).on('DOMNodeInserted', '.checklist', function() {
        initCollapsible();
    });
});
