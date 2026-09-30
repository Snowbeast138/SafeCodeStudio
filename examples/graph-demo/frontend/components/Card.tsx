import type { Task } from "../shared/types";
import { label } from "../shared/format.js";
export const Card = ({task}: {task: Task}) => <article>{label(task)}</article>;
