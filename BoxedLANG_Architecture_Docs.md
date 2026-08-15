# BoxedLANG Programmer's Reference

### For the BX Programming Language

**Version:** Current BoxedLANG syntax
**File extension:** `.bx`

---

# Contents

1. Introduction
2. Your First BX Program
3. BX Program Structure
4. Syntax
5. Boxes
6. Printing
7. Input
8. Mathematics
9. Conditions
10. TEST
11. IF
12. JUMP
13. JUMPIF
14. Marks
15. Deleting Boxes
16. Clearing the Screen
17. Ending a Program
18. Imports
19. Functions and RETURN
20. String Substitution
21. Colons and Escaping
22. Comments
23. Operators
24. Short Command Names
25. Command Reference
26. How BX Executes Programs
27. The AST
28. Program Counter and Marks
29. Transpilation
30. Variable Promotion
31. BX Programming Model
32. Quick Reference
33. Example Programs
34. Step-by-Step Walkthrough: Boxed OS
35. Step-by-Step Walkthrough: FizzBuzz
36. Complete BX Example

---

# 1. Introduction

BX, or **BoxedLANG**, is a small command-oriented programming language built around the concept of **boxes**.

A box stores a value under a name.

For example:

```bx
box name|mc20000
```

creates a box named `name` containing:

```text
mc20000
```

The value can then be inserted into another command using `$`:

```bx
say Hello $name
```

which produces:

```text
Hello mc20000
```

BX programs are made from individual commands. Arguments are normally separated using the `|` character.

A simple BX program:

```bx
box name|world
say Hello $name
end
```

produces:

```text
Hello world
```

BX is intentionally small at the source level. More complicated behavior is created by combining a few basic mechanisms:

* boxes
* commands
* conditions
* marks
* jumps
* imports
* function calls

---

# 2. Your First BX Program

Create a file named:

```text
hello.bx
```

Put this inside:

```bx
box name|BX
say Hello from $name!
end
```

The program performs three operations:

1. Creates a box called `name`.
2. Prints a message containing the box.
3. Ends the program.

Output:

```text
Hello from BX!
```

---

# 3. BX Program Structure

A BX program is normally a sequence of commands:

```text
command arguments
```

Arguments are separated with `|`.

For example:

```bx
box score|100
```

contains:

```text
command  = box
argument = score
argument = 100
```

Another example:

```bx
math result|10|5|+
```

contains:

```text
command  = math
target   = result
left     = 10
right    = 5
operator = +
```

Commands are generally separated from their arguments by whitespace.

---

# 4. Syntax

## 4.1 General Command Syntax

The general form of a BX command is:

```text
COMMAND ARGUMENT|ARGUMENT|ARGUMENT...
```

For example:

```bx
say Hello|0
```

---

## 4.2 Case

Commands are normalized by the parser, so command names are not normally case-sensitive.

For example:

```bx
SAY Hello
```

and:

```bx
say Hello
```

refer to the same command.

---

## 4.3 Argument Separator

The vertical bar is BX's normal argument separator:

```text
|
```

Example:

```bx
math answer|20|5|+
```

---

## 4.4 Empty and Optional Arguments

Some commands have optional arguments.

For example, `say` may omit its delay:

```bx
say Hello
```

The runtime uses its normal/default output timing.

An explicit zero delay can also be supplied:

```bx
say Hello|0
```

These are both valid BX.

---

## 4.5 Whitespace in Values

Whitespace inside a value is preserved exactly as written.

For example:

```bx
box message|Hello     world
```

stores:

```text
Hello     world
```

The spaces between `Hello` and `world` are not automatically collapsed.

The `|` character is the value delimiter, so spaces do not terminate a value.

For example:

```bx
box file-usr|usr: $login   pwd: $password
```

preserves the spaces in the value.

This distinction is important when writing a BX parser.

---

# 5. Boxes

Boxes are BX's primary storage mechanism.

## BOX

### Syntax

```text
box NAME|VALUE
```

Short form:

```text
b NAME|VALUE
```

Example:

```bx
box score|100
```

The box now contains:

```text
score = 100
```

---

## Reading a Box

Place `$` before the box name:

```bx
box name|Jay
say Hello $name
```

Output:

```text
Hello Jay
```

---

## Changing a Box

Assigning to an existing box replaces its previous value:

```bx
box score|10
box score|20
say $score
```

Output:

```text
20
```

---

## Boxes Containing Other Boxes

A box may contain text referring to another box:

```bx
box name|Jay
box message|Hello $name
say $message
```

The `$name` inside `message` is resolved when the value is evaluated.

---

## Dynamic Box Names

Box names can themselves contain substitutions:

```bx
box name|score
box $name|100
```

The resulting box is effectively:

```text
score = 100
```

This is useful for dynamically generated storage.

For example:

```bx
box name|file-test
box $name|hello
```

creates a box named:

```text
file-test
```

---

# 6. Printing

## SAY

Prints text to the output.

### Syntax

```text
say VALUE
```

or:

```text
say VALUE|DELAY
```

Short form:

```text
s VALUE|DELAY
```

Example:

```bx
say Hello
```

Output:

```text
Hello
```

---

## Print Delay

The second argument specifies an optional delay after printing.

Example:

```bx
say Hello|1
```

The runtime prints:

```text
Hello
```

and then waits for the specified amount of time.

A zero value means no delay:

```bx
say Hello|0
```

---

## Delay Is Optional

The delay is **not required** for normal BX programs.

This is valid:

```bx
say Result = $result
```

The runtime uses its default output behavior.

This is also valid:

```bx
say Result = $result|0
```

The `|0` explicitly requests zero delay.

### Recommended Practice

For simple programs, omitting the delay is completely valid.

However, explicitly specifying the delay is **recommended for programs intended to be transpiled, run by multiple BX runtimes, or executed in other environments**.

For example:

```bx
say Result = $result|0
```

makes the intended timing explicit instead of relying on a runtime's default.

This is particularly useful when portability and predictable behavior matter.

---

## Variable Substitution

```bx
box name|Jay
say Hello $name!
```

Output:

```text
Hello Jay!
```

---

# 7. Input

## ASK

`ask` reads input from the user and stores it in a box.

### Syntax

```text
ask PROMPT TARGET
```

Short form:

```text
a PROMPT TARGET
```

The **last space-separated token** is always interpreted as the target box name.

Everything before that final token is interpreted as the input prompt.

This is different from normal `|`-delimited commands.

---

## Basic Input

For example:

```bx
ask What is your name name
```

means:

```text
prompt = "What is your name"
target = "name"
```

The entered value is stored in:

```text
$name
```

Another example:

```bx
ask Enter your password password
```

means:

```text
prompt = "Enter your password"
target = "password"
```

---

## Empty Prompt

If the command contains only one token after `ask`:

```bx
ask name
```

the final token is the target:

```text
target = name
prompt = ""
```

This is therefore valid and simply reads input into `name` without a normal prompt message.

---

## Multi-Word Prompts

The prompt can contain as many words as needed.

For example:

```bx
ask are you sure yes(y)/no(n) ?
```

means:

```text
prompt = "are you sure yes(y)/no(n)"
target = "?"
```

The entered value is therefore stored in:

```text
$?
```

The important rule is:

> **The final space-separated token is the target box. Everything before it is the prompt.**

---

## Input Prompt Suffix

The runtime normally appends an input suffix to prompts.

The special box:

```text
prm
```

can be used to customize that suffix.

For example:

```bx
box prm| >
ask What is your name name
```

changes the prompt suffix.

This is particularly useful for programs that want their own command-line style.

---

## Parsing ASK

A parser can conceptually process:

```bx
ask What is your name name
```

as:

```text
command = ASK
prompt  = "What is your name"
target  = "name"
```

And:

```bx
ask are you sure yes(y)/no(n) ?
```

as:

```text
command = ASK
prompt  = "are you sure yes(y)/no(n)"
target  = "?"
```

The final token is therefore not part of the prompt.

---

# 8. Mathematics

## MATH

Performs integer arithmetic.

### Syntax

```text
math TARGET|LEFT|RIGHT|OP
```

Short form:

```text
m TARGET|LEFT|RIGHT|OP
```

Example:

```bx
math result|10|5|+
```

stores:

```text
result = 15
```

---

## Arithmetic Operators

| Operator | Meaning          |
| -------- | ---------------- |
| `+`      | Addition         |
| `-`      | Subtraction      |
| `*`      | Multiplication   |
| `x`      | Multiplication   |
| `/`      | Integer division |
| `%`      | Modulo           |

Example:

```bx
math add|20|5|+
math sub|20|5|-
math mul|20|5|*
math div|20|5|/
math rem|20|6|%
```

---

## Integer Arithmetic

BX's runtime performs integer arithmetic.

For example:

```bx
math answer|10|3|/
```

produces:

```text
3
```

rather than a floating-point result.

---

## Division by Zero

The current runtime returns `0` when division or modulo would divide by zero.

For example:

```bx
math result|10|0|/
```

produces:

```text
0
```

---

# 9. Conditions

Conditions compare two values.

BX conditions are especially flexible because the operator can appear in **two different positions**.

This applies to condition parsing used by commands such as:

* `test`
* `if`
* `jumpif`

and other condition-based operations.

---

## 9.1 Operator in the Middle

The standard form is:

```text
LEFT|OP|RIGHT
```

For example:

```bx
$score|==|100
```

means:

```text
score == 100
```

Another example:

```bx
$score|>|50
```

means:

```text
score > 50
```

---

## 9.2 Operator at the End

BX also accepts:

```text
LEFT|RIGHT|OP
```

For example:

```bx
$score|100|==
```

means:

```text
score == 100
```

Likewise:

```bx
$score|50|>
```

means:

```text
score > 50
```

---

## 9.3 The Two Forms Are Equivalent

These two conditions represent the same comparison:

```text
LEFT|OP|RIGHT
```

and:

```text
LEFT|RIGHT|OP
```

For example:

```bx
$login|==|admin
```

and:

```bx
$login|admin|==
```

both mean:

```text
$login == admin
```

This is an important part of BX syntax because both forms can appear in real BX programs.

---

## 9.4 Comparison Operators

BX supports:

| Operator | Meaning               |
| -------- | --------------------- |
| `==`     | Equal                 |
| `!=`     | Not equal             |
| `>`      | Greater than          |
| `<`      | Less than             |
| `>=`     | Greater than or equal |
| `<=`     | Less than or equal    |

Every comparison operator can be written using either condition layout.

Examples:

```text
$score|==|100
$score|100|==

$score|!=|100
$score|100|!=

$score|>|100
$score|100|>

$score|<|100
$score|100|<

$score|>=|100
$score|100|>=

$score|<=|100
$score|100|<=
```

---

## 9.5 Numeric Comparisons

For:

```text
>
<
>=
<=
```

BX attempts to interpret both values numerically.

For example:

```bx
box score|75
if $score|>|50|say|Passed
```

The comparison is performed numerically.

---

## 9.6 Equality Comparisons

`==` and `!=` compare the resolved values directly.

For example:

```bx
box login|admin
if $login|==|admin|say|Welcome
```

---

# 10. TEST

`test` evaluates a condition and stores one of two values.

### Syntax

The normal form is:

```text
test TARGET|LEFT|OP|RIGHT|TRUE|FALSE
```

BX also supports the alternate condition layout:

```text
test TARGET|LEFT|RIGHT|OP|TRUE|FALSE
```

Short form:

```text
t TARGET|LEFT|OP|RIGHT|TRUE|FALSE
```

---

## Standard TEST

Example:

```bx
test result|10|>|5|YES|NO
say $result
```

Output:

```text
YES
```

The condition:

```text
10 > 5
```

was true, so `result` received:

```text
YES
```

---

## Alternate TEST Syntax

The operator can be placed at the end:

```bx
test result|10|5|>|YES|NO
```

This means the same thing:

```text
10 > 5
```

The two forms are therefore equivalent:

```bx
test result|10|>|5|YES|NO
```

and:

```bx
test result|10|5|>|YES|NO
```

---

## TEST with Variables

```bx
box score|75
test result|$score|>=|50|PASS|FAIL
say $result
```

Output:

```text
PASS
```

The alternate form works as well:

```bx
test result|$score|50|>=|PASS|FAIL
```

---

## Default TEST Values

`test` can use `1` and `0` as its basic true/false values.

For example:

```bx
test result|10|>|5
```

sets:

```text
result = 1
```

while:

```bx
test result|10|<|5
```

sets:

```text
result = 0
```

This makes `test` useful for creating boolean-style boxes.

---

## TEST as a Conditional Value

Conceptually:

```text
test result|condition|TRUE|FALSE
```

works similarly to:

```text
result = TRUE if condition is true
result = FALSE otherwise
```

It can therefore be used as a simple conditional-value operation.

---

# 11. IF

`if` executes a command when a condition is true.

### Syntax

Standard condition form:

```text
if LEFT|OP|RIGHT|COMMAND|ARGUMENTS...
```

Alternate condition form:

```text
if LEFT|RIGHT|OP|COMMAND|ARGUMENTS...
```

Short form:

```text
i LEFT|OP|RIGHT|COMMAND|ARGUMENTS...
```

---

## Standard IF

Example:

```bx
box score|100
if $score|>|50|say|You passed!
```

Output:

```text
You passed!
```

---

## Alternate IF Syntax

The operator may be moved to the end:

```bx
if $score|50|>|say|You passed!
```

This is equivalent to:

```bx
if $score|>|50|say|You passed!
```

---

## All Comparison Operators Work Both Ways

For example:

```bx
if $x|==|10|say|equal
if $x|10|==|say|equal

if $x|!=|10|say|different
if $x|10|!=|say|different

if $x|>|10|say|greater
if $x|10|>|say|greater

if $x|<|10|say|less
if $x|10|<|say|less

if $x|>=|10|say|high
if $x|10|>=|say|high

if $x|<=|10|say|low
if $x|10|<=|say|low
```

---

## IF Executes One Command

An `if` contains a command to execute when its condition succeeds.

For example:

```bx
if $loggedin|==|1|say|Welcome
```

The nested command is:

```text
say Welcome
```

If the condition is false, the nested command is skipped.

A jump can also be used as the nested command:

```bx
if $loggedin|==|2|jump|loggedin|m
```

---

# 12. JUMP

`jump` changes the current program position.

### Syntax

```text
jump TARGET
```

or:

```text
jump TARGET|m
```

Short form:

```text
j TARGET
```

or:

```text
j TARGET|m
```

The `|m` mode is **optional**.

---

## Line Jumps

When the target is a literal line number, no mode is needed.

Example:

```bx
jump 22
```

This jumps directly to line `22`.

This is the normal syntax for a line-number jump.

---

## Mark Jumps

Use:

```text
|m
```

when the target refers to a named mark.

Example:

```bx
jump loop|m
```

The runtime looks for:

```text
loop
```

in the mark table.

---

## Numeric Mark Names

A mark may also have a numeric name.

For example:

```bx
premark 22
```

can be targeted with:

```bx
jump 22|m
```

The `|m` tells the runtime that `22` is a **mark name**, rather than a literal line number.

Therefore:

```bx
jump 22
```

means:

> Jump to line 22.

While:

```bx
jump 22|m
```

means:

> Jump to the mark named `22`.

---

## JUMP Mode Rule

The rule is simple:

```text
TARGET
```

means a literal line-number target.

```text
TARGET|m
```

means a marked-line target.

Therefore:

```bx
jump 10
```

is a line jump.

And:

```bx
jump loop|m
```

is a mark jump.

---

# 13. JUMPIF

`jumpif` performs a conditional jump.

### Syntax

Standard form:

```text
jumpif LEFT|OP|RIGHT|TARGET
```

or:

```text
jumpif LEFT|OP|RIGHT|TARGET|m
```

Alternate form:

```text
jumpif LEFT|RIGHT|OP|TARGET
```

or:

```text
jumpif LEFT|RIGHT|OP|TARGET|m
```

Short form:

```text
ji LEFT|OP|RIGHT|TARGET
```

or:

```text
ji LEFT|OP|RIGHT|TARGET|m
```

The `|m` mode is **optional**.

---

## Line-Based JUMPIF

When jumping to a literal line number, omit `|m`.

Example:

```bx
jumpif $x|<|10|22
```

If the condition is true, execution jumps to line `22`.

---

## Mark-Based JUMPIF

When jumping to a mark, use `|m`.

Example:

```bx
jumpif $x|<|10|loop|m
```

If:

```text
x < 10
```

is true, execution jumps to the mark:

```text
loop
```

---

## Alternate Condition Form

The same jump can be written:

```bx
jumpif $x|10|<|loop|m
```

The operator is simply moved from the middle to the end of the condition.

---

## Numeric Mark Names

Numeric marks are also possible:

```bx
premark 22
```

Then:

```bx
jumpif $x|<|10|22|m
```

targets the mark named `22`.

Without the mode:

```bx
jumpif $x|<|10|22
```

targets literal line 22.

---

## Loops

`jumpif` is commonly combined with `premark` and `math` to create loops.

Example:

```bx
box i|0

premark loop

say $i
math i|$i|1|+
jumpif $i|<|10|loop|m

end
```

---

# 14. Marks

A mark gives a name to a location in a BX program.

## PREMARK

### Syntax

```text
premark NAME
```

Aliases:

```text
mark NAME
mk NAME
```

Example:

```bx
premark loop
```

The mark can then be targeted with:

```bx
jump loop|m
```

or:

```bx
jumpif $x|<|10|loop|m
```

---

## Marks as Named Addresses

A useful way to think about a mark is:

```text
premark loop
```

creates a named execution address:

```text
loop -> program position
```

This makes marks useful for:

* loops
* menus
* applications
* functions
* state machines
* branching programs

---

# 15. Deleting Boxes

## DEL

Deletes a box.

### Syntax

```text
del NAME
```

Short form:

```text
d NAME
```

Example:

```bx
box temp|123
del temp
```

After deletion, `temp` is no longer stored.

---

## Dynamic Deletion

Box names are resolved before deletion.

Example:

```bx
box name|temp
del $name
```

This deletes:

```text
temp
```

---

# 16. Clearing the Screen

## CLEAR

Clears the terminal screen.

### Syntax

```text
clear
```

Short form:

```text
cls
```

Example:

```bx
clear
```

The current runtime uses ANSI terminal control sequences to clear the screen and move the cursor to the home position.

---

# 17. Ending a Program

## END

Terminates the current program.

### Syntax

```text
end
```

Short form:

```text
e
```

Example:

```bx
say Program finished.
end
```

Once `end` executes, the program stops.

---

# 18. Imports

BX can import other `.bx` files.

### Syntax

```text
import PATH
```

or:

```text
import PATH|ALIAS
```

Short form:

```text
imp PATH|ALIAS
```

---

## Local Files

Example:

```bx
import math.bx
```

A `.bx` file can therefore be split into separate modules.

---

## Import Aliases

An import can be assigned a namespace:

```bx
import math.bx|math
```

A function from that module can then be called using:

```text
math.function
```

---

## Relative Paths

Example:

```bx
import ./lib/math.bx
```

The imported file is resolved relative to the importing file.

---

## Home-Relative Paths

Example:

```bx
import ~/mybx/math.bx
```

---

## Package Imports

A package-style import can use a bare name:

```bx
import graphics
```

The BX package system can resolve the package through the BX package directory.

---

## Import Processing

Imported BX source is parsed into the same overall program representation.

This means imported code can contribute:

* commands
* marks
* functions
* namespaces

---

# 19. Functions and RETURN

BX functions are represented using marks, particularly marks inside imported modules.

A namespaced call uses:

```text
namespace.function
```

For example:

```text
math.add
```

---

## CALL

A command containing a namespace and function name can be interpreted as a call.

Example:

```bx
math.add|10|20
```

Arguments are made available through:

```text
arg1
arg2
arg3
...
```

For example:

```text
arg1 = 10
arg2 = 20
```

---

## Function Example

A module can contain:

```bx
premark add

math ret-result|$arg1|$arg2|+
return
```

A caller can then invoke:

```bx
math.add|10|20
```

---

## RETURN

### Syntax

```text
return
```

Short form:

```text
ret
```

`return` exits the current function call and resumes execution at the calling location.

---

## Return Values

BX supports a `ret-` naming convention for returning values.

For example:

```bx
math ret-result|$arg1|$arg2|+
return
```

creates:

```text
ret-result
```

When returning, the runtime copies the value into:

```text
result
```

This provides a simple mechanism for returning data from functions.

---

# 20. String Substitution

BX uses `$` to reference boxes.

Example:

```bx
box name|Jay
say My name is $name.
```

Output:

```text
My name is Jay.
```

---

## Multiple Substitutions

```bx
box first|Hello
box second|world

say $first $second!
```

Output:

```text
Hello world!
```

---

## Dynamic References

Because box names can also be resolved, BX can build references dynamically.

Example:

```bx
box name|message
box message|Hello
say $$name
```

The reference can resolve through more than one level.

This is useful for structures such as:

```text
name -> message -> actual value
```

---

## Double Indirection

The runtime performs resolution repeatedly.

For example:

```bx
box name|message
box message|Hello
say $$name
```

conceptually goes through:

```text
$$name
   |
   v
$message
   |
   v
Hello
```

This makes dynamic storage structures possible without requiring a separate pointer syntax.

---

# 21. Colons and Escaping

BX has special handling for `:` characters in resolved strings.

An unescaped colon is removed during runtime string resolution.

To preserve a literal colon, use:

```text
\/:
```

Example:

```bx
say hello\/:world
```

produces:

```text
hello:world
```

---

## Why This Happens

The runtime protects escaped colons temporarily, removes unescaped colons, then restores the escaped ones.

Conceptually:

```text
\/:
```

becomes a temporary protected character.

Then normal:

```text
:
```

characters are removed.

Finally the protected character becomes:

```text
:
```

again.

---

## Example

This:

```bx
say -----------:$name:-----------
```

would have its colons stripped.

To preserve them:

```bx
say -----------\/:$name\/:-----------
```

produces the intended colon characters.

---

# 22. Comments

BX uses `//` for comments.

A complete comment line can be:

```bx
// this is a comment
```

Comments can also follow code:

```bx
say Hello // print greeting
```

Everything after `//` is treated as a comment.

Comments are especially useful for documenting marks:

```bx
premark app-calc // calculator app
```

---

# 23. Operators

## Comparison Operators

```text
==    equal
!=    not equal
>     greater than
<     less than
>=    greater than or equal
<=    less than or equal
```

Each comparison operator can appear in either supported condition layout:

```text
LEFT|OP|RIGHT
```

or:

```text
LEFT|RIGHT|OP
```

---

## Mathematical Operators

```text
+     addition
-     subtraction
*     multiplication
x     multiplication
/     integer division
%     modulo
```

---

# 24. Short Command Names

BX provides short aliases for common commands.

| Full Command | Short Form   |
| ------------ | ------------ |
| `box`        | `b`          |
| `say`        | `s`          |
| `ask`        | `a`          |
| `math`       | `m`          |
| `test`       | `t`          |
| `if`         | `i`          |
| `jump`       | `j`          |
| `jumpif`     | `ji`         |
| `del`        | `d`          |
| `premark`    | `mark`, `mk` |
| `end`        | `e`          |
| `clear`      | `cls`        |
| `return`     | `ret`        |
| `import`     | `imp`        |

---

# 25. Command Reference

## BOX

```text
box NAME|VALUE
```

Creates or replaces a box.

---

## SAY

```text
say VALUE
```

or:

```text
say VALUE|DELAY
```

Prints a value.

The delay is optional.

An explicit `|0` requests zero delay.

For portable or transpiled programs, specifying the delay is recommended.

---

## ASK

```text
ask PROMPT TARGET
```

Reads user input into a box.

The final space-separated token is the target box.

Everything before the final token is the prompt.

Example:

```bx
ask What is your name name
```

means:

```text
prompt = "What is your name"
target = "name"
```

A single-token form:

```bx
ask name
```

means:

```text
prompt = ""
target = "name"
```

A multi-word prompt can therefore be used:

```bx
ask are you sure yes(y)/no(n) ?
```

which targets:

```text
?
```

---

## MATH

```text
math TARGET|LEFT|RIGHT|OP
```

Performs integer arithmetic.

---

## TEST

```text
test TARGET|LEFT|OP|RIGHT|TRUE|FALSE
```

or:

```text
test TARGET|LEFT|RIGHT|OP|TRUE|FALSE
```

Stores a value based on a condition.

---

## IF

```text
if LEFT|OP|RIGHT|COMMAND|ARGS...
```

or:

```text
if LEFT|RIGHT|OP|COMMAND|ARGS...
```

Executes a command if the condition is true.

---

## JUMP

```text
jump TARGET
```

Jumps to a literal line number.

Or:

```text
jump TARGET|m
```

Jumps to a marked line.

The `|m` mode is optional when the target is a literal line number.

---

## JUMPIF

```text
jumpif LEFT|OP|RIGHT|TARGET
```

or:

```text
jumpif LEFT|OP|RIGHT|TARGET|m
```

Also:

```text
jumpif LEFT|RIGHT|OP|TARGET
```

or:

```text
jumpif LEFT|RIGHT|OP|TARGET|m
```

Conditionally changes execution position.

---

## PREMARK

```text
premark NAME
```

Creates a named execution location.

---

## DEL

```text
del NAME
```

Deletes a box.

---

## CLEAR

```text
clear
```

Clears the terminal.

---

## END

```text
end
```

Stops the program.

---

## IMPORT

```text
import PATH
```

or:

```text
import PATH|ALIAS
```

Loads another BX module.

---

## RETURN

```text
return
```

Returns from a function call.

---

# 26. How BX Executes Programs

BX source is not normally executed directly as raw text.

The basic execution pipeline is:

```text
BX SOURCE
    |
    v
PARSER
    |
    v
AST
    |
    v
BX RUNTIME
    |
    v
EXECUTION
```

The AST provides a structured representation of the program.

This allows the parser and runtime to have separate responsibilities:

```text
Parser  -> understands BX syntax
AST     -> represents BX operations
Runner  -> executes BX operations
```

The same AST can also be used by a transpiler.

---

# 27. The AST

The parser converts source commands into AST nodes.

For example:

```bx
box score|100
```

becomes conceptually:

```text
{
    "type": "Assign",
    "target": "score",
    "value": "100"
}
```

A `say` command becomes a `Print` node.

A `math` command becomes a `Math` node.

An `if` command becomes an `If` node.

A `jumpif` command becomes a `JumpIf` node.

An `ask` command can be represented conceptually as:

```text
{
    "type": "Ask",
    "prompt": "What is your name",
    "target": "name"
}
```

for:

```bx
ask What is your name name
```

This separation is important because the runtime does not need to understand the original source syntax once parsing has finished.

---

# 28. Program Counter and Marks

The runtime keeps track of its current position using a program index.

Conceptually:

```text
line_index = 0
```

The runtime executes the AST at that position:

```text
AST[line_index]
```

Normally, execution continues forward:

```text
line_index += 1
```

A jump changes this position.

For example:

```bx
jump loop|m
```

looks up the mark:

```text
loop
```

and changes the current execution position.

---

## Mark Table

When the parser sees:

```bx
premark loop
```

it records the location in a mark table.

Conceptually:

```text
marks["loop"] = AST position
```

A mark is therefore similar to a named address.

---

## Line Jumps

A line jump does not use the mark table.

For example:

```bx
jump 22
```

targets the literal line number `22`.

The distinction is:

```text
jump 22
```

→ line 22

```text
jump 22|m
```

→ mark named `22`

This allows numeric mark names without making them ambiguous with line targets.

---

## Jumps and the Program Counter

A BX jump does not require a native `goto`.

Instead:

```text
jump
   |
   v
determine target mode
   |
   +---- line mode ----> line number
   |
   +---- mark mode ----> mark table
   |
   v
change program position
   |
   v
execute target
```

This allows BX to implement:

* loops
* menus
* branches
* state machines
* function calls

using the same execution mechanism.

---

# 29. Transpilation

BX can also be translated into other programming languages.

The interpreter and transpiler share the AST representation.

## Interpreter

```text
.bx
 |
 v
AST
 |
 v
BX Runner
 |
 v
Program execution
```

## Transpiler

```text
.bx
 |
 v
AST
 |
 v
Transpiler
 |
 v
Generated source
 |
 v
Target runtime
```

This architecture means the parser defines BX's source-level structure while different backends can decide how that structure is executed.

---

## Explicit Timing and Transpilation

Commands with optional runtime behavior can be made more portable by explicitly specifying their parameters.

For example:

```bx
say Hello|0
```

is preferable to:

```bx
say Hello
```

when generating code for another runtime where output timing may otherwise have different defaults.

The delay is still optional in BX source.

---

# 30. Variable Promotion

A transpiler can optimize statically named boxes.

For example:

```bx
box login|mc20000
```

can conceptually become:

```python
bx_login = "mc20000"
```

instead of requiring a dictionary lookup every time.

---

## Dynamic Boxes

A dynamically generated box name cannot always become one fixed native variable.

For example:

```bx
box note-$name|hello
```

depends on the runtime value of:

```text
$name
```

Conceptually, this requires dynamic storage:

```python
boxes["note-" + name] = "hello"
```

This allows BX to support dynamic names while still allowing simple variables to be optimized.

---

# 31. BX Programming Model

BX can be understood as a small set of fundamental mechanisms.

```text
BOX
 |
 +--> store data

SAY
 |
 +--> output data

ASK
 |
 +--> receive data

MATH
 |
 +--> calculate

TEST
 |
 +--> produce a value from a condition

IF
 |
 +--> conditionally execute a command

PREMARK
 |
 +--> create an execution address

JUMP
 |
 +--> change execution position

JUMPIF
 |
 +--> conditionally change execution position

IMPORT
 |
 +--> load another BX program

CALL / RETURN
 |
 +--> execute reusable code
```

Most larger BX programs are combinations of these basic operations.

---

# 32. Quick Reference

## Boxes

```bx
box NAME|VALUE
b NAME|VALUE
```

## Output

```bx
say TEXT
say TEXT|TIME
s TEXT
```

The delay is optional.

For portable/transpiled programs:

```bx
say TEXT|0
```

is recommended when zero delay is intended.

## Input

```bx
ask TARGET
ask PROMPT TARGET
a TARGET
a PROMPT TARGET
```

The final space-separated token is always the target.

Examples:

```bx
ask name
```

and:

```bx
ask What is your name name
```

---

## Mathematics

```bx
math TARGET|LEFT|RIGHT|OP
m TARGET|LEFT|RIGHT|OP
```

## TEST

```bx
test TARGET|LEFT|OP|RIGHT|TRUE|FALSE
test TARGET|LEFT|RIGHT|OP|TRUE|FALSE
t TARGET|LEFT|OP|RIGHT|TRUE|FALSE
```

## IF

```bx
if LEFT|OP|RIGHT|COMMAND|ARGS...
if LEFT|RIGHT|OP|COMMAND|ARGS...
i LEFT|OP|RIGHT|COMMAND|ARGS...
```

## JUMP

Line-number target:

```bx
jump TARGET
j TARGET
```

Mark target:

```bx
jump TARGET|m
j TARGET|m
```

## JUMPIF

Line-number target:

```bx
jumpif LEFT|OP|RIGHT|TARGET
jumpif LEFT|RIGHT|OP|TARGET
```

Mark target:

```bx
jumpif LEFT|OP|RIGHT|TARGET|m
jumpif LEFT|RIGHT|OP|TARGET|m
```

Short form:

```bx
ji LEFT|OP|RIGHT|TARGET
ji LEFT|OP|RIGHT|TARGET|m
```

## Marks

```bx
premark NAME
mark NAME
mk NAME
```

## Delete

```bx
del NAME
d NAME
```

## Clear

```bx
clear
cls
```

## End

```bx
end
e
```

## Import

```bx
import PATH
import PATH|ALIAS
imp PATH|ALIAS
```

## Functions

```bx
namespace.function|ARGS...
return
ret
```

---

# 33. Example Programs

This section contains complete BX programs demonstrating how the language can be used.

The examples intentionally use the same mechanisms described above rather than introducing additional syntax.

---

## Example 1 — Hello World

```bx
say Hello, world!
end
```

Output:

```text
Hello, world!
```

---

## Example 2 — Variables

```bx
box name|Jay
box age|15

say Name = $name
say Age = $age

end
```

---

## Example 3 — Calculator

```bx
box a|20
box b|7

math add|$a|$b|+
math sub|$a|$b|-
math mul|$a|$b|*
math div|$a|$b|/
math rem|$a|$b|%

say ADD = $add
say SUB = $sub
say MUL = $mul
say DIV = $div
say REM = $rem

end
```

---

## Example 4 — TEST

```bx
box score|75

test result|$score|>=|50|PASS|FAIL

say Result = $result

end
```

The same condition can use the alternate layout:

```bx
test result|$score|50|>=|PASS|FAIL
```

---

## Example 5 — IF

```bx
box score|100

if $score|>=|90|say|Excellent!
if $score|<|90|say|Keep practicing!

end
```

---

## Example 6 — Alternate IF Syntax

```bx
box score|100

if $score|90|>=|say|Excellent!
if $score|90|<|say|Keep practicing!

end
```

The comparison operator is at the end of each condition.

---

## Example 7 — Counting Loop

```bx
box i|0

premark loop

say $i
math i|$i|1|+

jumpif $i|<|10|loop|m

say Finished.
end
```

Output:

```text
0
1
2
3
4
5
6
7
8
9
Finished.
```

---

# 34. Step-by-Step Walkthrough: Boxed OS

The following example is a larger BX program demonstrating how boxes, dynamic names, marks, jumps, input, applications, and nested control flow can be combined.

```bx
box prm| \\/:>

import apps|app-

say booting boxed-os  ver 0.01 sky|1
ask login
ask password
box file-usr|usr: $login   pwd: $password

clear

test lg|$login|admin|==|1|0
test in|$password|1234|==|1|0
math loggedin|$lg|$in|+
if $loggedin|==|2|jump|loggedin|m
say bad login or error|0
say ending os loop|0
if $loggedin|!=|2|jump|loggedfail|m


premark app-calc // calculator app
ask #1
ask op
ask #2
math calc|$#1|$#2|$op
say $calc|0
jump boot|m


premark app-note // note app
premark app-notes
ask write(w)/read(r) ?
jump notes-:$?|m

premark notes-w // write a note
ask note name
ask note
box note-:$name|$note
say done writing|0
jump boot|m

premark notes-r // read a note
ask name
box name|note-:$name
say |0
say -----------:$name:-----------|0
say $$name|0
say |0
jump boot|m


premark app-file // file app
premark app-files
ask read(r)/write(w)/del(d) ?
jump files-:$?|m

premark files-r
ask name
box name|file-:$name
say |0
say -----------:$name:-----------|0
say $$name|0
say |0
jump boot|m

premark files-w
ask name
ask data
box file-:$name|$data
say done writing|0
jump boot|m

premark files-d
ask name
ask are you sure yes(y)/no(n) ?
box name|file-:$name
if $?|==|n|jump|boot|m
if $?|==|y|del|$name
say deleted $name|0
jump boot|m


premark app-end // end app
end now


premark boot
ask name of app
jump app-$app|m
box name|
box data|
box note|
box ?|
jump boot|m
say error loop ended
end now

premark loggedin
say |0
say welcome $login|0
say |0
jump boot|m

premark loggedfail
say loggin fail
end now
```

---

## 34.1 Setting the Prompt

The program begins with:

```bx
box prm| \\/:>
```

The `prm` box changes the input prompt suffix.

The `\/:` sequence preserves the literal colon.

---

## 34.2 Loading a Module

The program then uses:

```bx
import apps|app-
```

This loads another BX module using the namespace:

```text
app-
```

The imported program can provide application marks that the main program jumps to.

---

## 34.3 Login

The program asks for:

```bx
ask login
ask password
```

Under the `ASK` parsing rule, these are single-token forms.

Therefore:

```text
ask login
```

means:

```text
prompt = ""
target = login
```

and:

```text
ask password
```

means:

```text
prompt = ""
target = password
```

These create the boxes:

```text
login
password
```

The entered values are then placed into another dynamically constructed box:

```bx
box file-usr|usr: $login   pwd: $password
```

This stores information under the box name:

```text
file-usr
```

The spaces between the username and password fields are preserved as written.

---

## 34.4 Checking the Login

Two `test` commands create boolean-style values:

```bx
test lg|$login|admin|==|1|0
test in|$password|1234|==|1|0
```

The first checks whether:

```text
login == admin
```

The second checks whether:

```text
password == 1234
```

The results are:

```text
lg = 1 or 0
in = 1 or 0
```

They are then combined:

```bx
math loggedin|$lg|$in|+
```

A successful login therefore produces:

```text
loggedin = 2
```

---

## 34.5 Selecting the Login Result

The program checks:

```bx
if $loggedin|==|2|jump|loggedin|m
```

If both tests succeeded, execution jumps to the:

```text
loggedin
```

mark.

The `|m` is required here because `loggedin` is a mark rather than a literal line number.

Otherwise the program prints:

```text
bad login or error
```

and eventually jumps to:

```text
loggedfail
```

---

## 34.6 The Application System

The main application loop is:

```bx
premark boot
ask name of app
jump app-$app|m
```

The entered application name is inserted into the jump target.

For example, if:

```text
app = calc
```

then:

```text
app-$app
```

resolves to:

```text
app-calc
```

and:

```bx
jump app-$app|m
```

jumps to:

```text
app-calc
```

This is an example of using **dynamic mark names**.

---

## 34.7 Calculator

The calculator begins at:

```bx
premark app-calc
```

It asks for two values and an operator:

```bx
ask #1
ask op
ask #2
```

Each of these is a single-token `ASK`, so the final token is the destination box.

Then:

```bx
math calc|$#1|$#2|$op
```

uses the entered operator as the mathematical operation.

The result is printed:

```bx
say $calc|0
```

and the application returns to:

```bx
jump boot|m
```

---

## 34.8 Notes

The note application creates another menu:

```bx
premark app-note
premark app-notes
ask write(w)/read(r) ?
jump notes-:$?|m
```

The `ASK` command:

```bx
ask write(w)/read(r) ?
```

is parsed as:

```text
prompt = "write(w)/read(r)"
target = "?"
```

If the user enters:

```text
w
```

the target becomes:

```text
notes-w
```

If the user enters:

```text
r
```

the target becomes:

```text
notes-r
```

This is another example of dynamically constructing a mark name.

---

## 34.9 Writing Notes

The write section asks for:

```bx
ask note name
ask note
```

The first means:

```text
prompt = "note"
target = "name"
```

The second means:

```text
prompt = ""
target = "note"
```

The result is stored using a dynamic box name:

```bx
box note-:$name|$note
```

If:

```text
name = test
```

then the box becomes:

```text
note-test
```

---

## 34.10 Reading Notes

The read section creates a reference:

```bx
box name|note-:$name
```

Then:

```bx
say $$name|0
```

uses double indirection.

If:

```text
name = note-test
```

then:

```text
$name
```

resolves to:

```text
note-test
```

and:

```text
$$name
```

can then resolve the dynamically referenced box.

---

## 34.11 Files

The file application uses the same dynamic-box technique.

Writing:

```bx
box file-:$name|$data
```

creates a dynamically named box.

Reading:

```bx
box name|file-:$name
say $$name|0
```

retrieves it through indirection.

Deleting:

```bx
del $name
```

deletes the dynamically selected box.

---

## 34.12 Confirmation Input

This line:

```bx
ask are you sure yes(y)/no(n) ?
```

is parsed as:

```text
prompt = "are you sure yes(y)/no(n)"
target = "?"
```

Therefore the result is available as:

```text
$?
```

The program then checks:

```bx
if $?|==|n|jump|boot|m
if $?|==|y|del|$name
```

The first condition jumps back to the `boot` mark if the user answered `n`.

The second deletes the selected box if the user answered `y`.

---

## 34.13 Returning to the Main Menu

Most applications finish with:

```bx
jump boot|m
```

This returns execution to:

```text
premark boot
```

The user can then choose another application.

This is effectively a simple application dispatcher built entirely from:

```text
premark
ask
jump
```

and dynamic names.

---

# 35. Step-by-Step Walkthrough: FizzBuzz

The following is a compact BX implementation of FizzBuzz:

```bx
box i|0
math i|$i|1|+
jumpif $i|10000|>|17
math r3|$i|3|%
math r5|$i|5|%
jumpif $r3|==|0|10
jumpif $r5|==|0|13
say $i
jump 2
jumpif $r5|==|0|15
say Fizz
jump 2
say Buzz
jump 2
say FizzBuzz
jump 2
```

The jumps in this example intentionally use **line-number mode**, so they omit `|m`.

For example:

```bx
jump 2
```

means:

> Jump to literal line 2.

And:

```bx
jumpif $r3|==|0|10
```

means:

> If `$r3 == 0`, jump to literal line 10.

---

## 35.1 Starting the Counter

The program starts with:

```bx
box i|0
```

Then increments it:

```bx
math i|$i|1|+
```

The first value becomes:

```text
1
```

---

## 35.2 Looping

The program uses:

```bx
jumpif $i|10000|>|17
```

This is a line-number conditional jump.

The comparison uses the alternate condition syntax:

```text
LEFT|RIGHT|OP
```

So:

```text
$i|10000|>
```

means:

```text
$i > 10000
```

The target `17` is interpreted as a literal line number because no `|m` is present.

---

## 35.3 Testing Divisibility

The program calculates:

```bx
math r3|$i|3|%
math r5|$i|5|%
```

These store the remainders from division by:

```text
3
5
```

If a remainder is zero, the number is divisible by that value.

---

## 35.4 FizzBuzz Branching

The program then checks:

```bx
jumpif $r3|==|0|10
jumpif $r5|==|0|13
```

These are line-number jumps.

The program ultimately prints:

```text
Fizz
Buzz
FizzBuzz
```

or the number itself.

---

# 36. Complete BX Example

This program combines boxes, arithmetic, conditions, a loop, dynamic values, and program termination:

```bx
clear

box name|BX
box count|0

say Welcome to $name!

premark loop

math count|$count|1|+
say Count = $count

test done|$count|>=|5|1|0

if $done|==|1|jump|finished|m

jump loop|m

premark finished

say Finished counting!
end
```

Execution proceeds roughly as:

```text
clear screen
     |
     v
create name
     |
     v
create count
     |
     v
print greeting
     |
     v
loop
     |
     v
increment count
     |
     v
print count
     |
     v
test whether count >= 5
     |
     +---- false ----> loop
     |
     +---- true -----> finished
                           |
                           v
                    print completion
                           |
                           v
                          end
```

The important part of BX programming is that the language does not require a special `while`, `for`, or `switch` construct to build this kind of behavior.

The combination of:

```text
premark
jump
jumpif
if
test
math
```

is enough to construct the control flow.

---

# Final Syntax Rules

The following rules summarize several important details of BX syntax.

## ASK

The final space-separated token is always the target box.

```bx
ask What is your name name
```

means:

```text
prompt = "What is your name"
target = "name"
```

And:

```bx
ask are you sure yes(y)/no(n) ?
```

means:

```text
prompt = "are you sure yes(y)/no(n)"
target = "?"
```

---

## JUMP

A literal line number does not require a mode:

```bx
jump 22
```

A marked target uses `|m`:

```bx
jump loop|m
```

Even a numeric mark uses `|m`:

```bx
premark 22
jump 22|m
```

Therefore:

```text
TARGET       = line target
TARGET|m     = mark target
```

---

## JUMPIF

The same rule applies to conditional jumps:

```bx
jumpif $x|==|5|22
```

means:

> If `$x == 5`, jump to line 22.

While:

```bx
jumpif $x|==|5|loop|m
```

means:

> If `$x == 5`, jump to the mark `loop`.

---

## SAY

The delay is optional:

```bx
say Hello
```

is valid.

An explicit delay can be supplied:

```bx
say Hello|0
```

For programs intended to be **transpiled, portable, or executed under different runtimes**, explicitly specifying the delay is recommended when predictable timing is desired.

---

## Values

Whitespace inside values is preserved exactly:

```bx
box text|Hello     world
```

stores:

```text
Hello     world
```

The `|` delimiter separates arguments; ordinary spaces inside a value do not automatically get removed or collapsed.

---

# End of Programmer's Reference

BoxedLANG is fundamentally built around a small execution model:

```text
BOX
  ↓
store data

SAY
  ↓
output data

ASK
  ↓
receive data

MATH
  ↓
calculate

TEST
  ↓
produce conditional values

IF
  ↓
conditionally execute commands

PREMARK
  ↓
create named execution addresses

JUMP / JUMPIF
  ↓
change execution position

IMPORT
  ↓
load additional code

CALL / RETURN
  ↓
execute reusable code
```

With these mechanisms, BX can represent simple scripts as well as larger programs containing menus, applications, loops, dynamic storage, modules, and reusable code.
