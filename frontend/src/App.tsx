import { useSystemStore } from "./store/system";

export default function App() {
  const { fsmState, isConnected } = useSystemStore();

  return (
    <main>
      <h1>Grimoire</h1>
      <p>FSM: {fsmState}</p>
      <p>WS: {isConnected ? "connected" : "disconnected"}</p>
    </main>
  );
}
