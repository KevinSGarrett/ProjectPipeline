
package main
import("encoding/json";"fmt";"os")
type Event struct{ID string `json:"id"`;IncidentID string `json:"incident_id"`;Type string `json:"type"`}
func main(){var e Event;_ = json.Unmarshal([]byte(os.Args[1]),&e);f,_:=os.OpenFile("delivered.log",os.O_CREATE|os.O_APPEND|os.O_WRONLY,0644);defer f.Close();fmt.Fprintln(f,e.ID,e.IncidentID,e.Type)}
