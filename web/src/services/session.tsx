import { createContext, useContext, type ReactNode } from "react";
import { AuthRequiredError } from "./api";
import { errorMessage } from "./messages";

type Session = {
  /** Turn an error into copy; a 401 also sends the app back to the connect panel. */
  explain: (err: unknown) => string;
};

const SessionContext = createContext<Session>({ explain: errorMessage });

export function SessionProvider({
  onAuthLost,
  children,
}: {
  onAuthLost: () => void;
  children: ReactNode;
}) {
  const explain = (err: unknown) => {
    if (err instanceof AuthRequiredError) onAuthLost();
    return errorMessage(err);
  };
  return <SessionContext.Provider value={{ explain }}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  return useContext(SessionContext);
}
