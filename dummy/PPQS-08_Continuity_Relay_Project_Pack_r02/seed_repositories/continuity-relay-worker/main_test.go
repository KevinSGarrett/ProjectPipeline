
package main
import("testing";"time")
func TestFlakyTiming(t *testing.T){time.Sleep(time.Duration(time.Now().UnixNano()%3)*time.Millisecond);if time.Now().UnixNano()%17==0{t.Fatal("intermittent timing failure")}}
