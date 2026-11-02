import { AudioLines, MessageSquare } from "lucide-react";

export const TalkIcon = () => (
  <AudioLines
    size={13}
    className="mr-2 opacity-85 select-none pointer-events-none transition-transform duration-300 group-hover:scale-110"
  />
);

export const ChatIcon = () => (
  <MessageSquare
    size={13}
    className="mr-2 opacity-85 select-none pointer-events-none transition-transform duration-300 group-hover:scale-110"
  />
);
