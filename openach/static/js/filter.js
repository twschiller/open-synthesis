
$(document).ready(function(){
        $("#status").change(function(){
            $(this).find("option:selected").each(function(){
                var optionValue = $(this).attr("value");
                var table, rows, switching, i, x, y, shouldSwitch;
                table = document.getElementById("myTable");
                switching = true;
                while (switching) {
                    switching = false;
                    rows = table.rows;
                    for (i = 1; i < (rows.length - 1); i++) {
                        if(optionValue == "byDate"){
                            shouldSwitch = false;
                            x = rows[i].getElementsByTagName("TD")[1];
                            y = rows[i + 1].getElementsByTagName("TD")[1];
                            if (x.innerHTML.toLowerCase() < y.innerHTML.toLowerCase()) {
                                shouldSwitch = true;
                                break;
                            }
                            console.log(x, y);
                        } else{
                            shouldSwitch = false;
                            x = rows[i].getElementsByTagName("TD")[3];
                            y = rows[i + 1].getElementsByTagName("TD")[3];
                            if (x.innerHTML.toLowerCase() < y.innerHTML.toLowerCase()) {
                                    shouldSwitch = true;
                                    break;
                                }
                                console.log(x, y);
                        }
                    }
                    if (shouldSwitch) {
                        rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                        switching = true;
                    }
                };
        });
    });
});